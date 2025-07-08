import os
import socket
import network
import ujson as json
import time

DEFAULT_CREDENTIAL_LOCATION = "wifi.json"
DEFAULT_CONNECTION_TIMEOUT_SECONDS = 30

DEFAULT_ADHOC_SSID = "PicoWifi Adhoc"
DEFAULT_ADHOC_PASSWORD = "1234567890"
DEFAULT_ADHOC_IFCONFIG = ("192.168.1.1", "255.255.255.0", "192.168.1.1", "8.8.8.8")

# Status values for the network state
STA_DISCONNECTED = 1
STA_CONNECTING = 2
STA_CONNECTED = 3
STA_ACCESSPOINT = 4

# Log levels
LOG_NONE = 1
LOG_ERROR = 2
LOG_INFO = 3
LOG_DEBUG = 4

# Should probably be a singleton since it has access to the network hardware
class PicoWifi:
    def __init__(self,
                 credentials_file=DEFAULT_CREDENTIAL_LOCATION,
                 connection_timeout=DEFAULT_CONNECTION_TIMEOUT_SECONDS,
                 adhoc_ifconfig=DEFAULT_ADHOC_IFCONFIG,
                 adhoc_ssid=DEFAULT_ADHOC_SSID,
                 adhoc_password=DEFAULT_ADHOC_PASSWORD,
                 credentials_page_server_port=80,
                 log_level=LOG_ERROR):
        try:
            self.credentials = WifiCredentials.fromFile(credentials_file)
        except Exception:
            self.credentials = None

        self.log_level = log_level
        self.credentials_file = credentials_file

        self.adhoc_ifconfig = adhoc_ifconfig
        self.adhoc_ssid = adhoc_ssid
        self.adhoc_password = adhoc_password
        self.connection_timeout = connection_timeout
        self.credentials_page_server_port = credentials_page_server_port

        self.__connection_state = STA_DISCONNECTED

        self.__adhoc_ap = network.WLAN(network.AP_IF)
        self.__wifi_connection = network.WLAN(network.STA_IF)

        self.__setWifiConfig()
        self.__setAdhocConfig()

    def init(self):
        while True:
            try:
                self.__log(LOG_INFO, "Connecting to wifi...")
                self.connectToWifi()
                self.__log(LOG_INFO, "Connected!")
                return
            except NoWifiCredentialsException:
                self.__log(LOG_ERROR,"No credentials present")
            except IncorrectWifiPasswordException:
                self.__log(LOG_ERROR, "Password is incorrect")
            except UnknownWifiConnectionFailureException as exc:
                self.__log(LOG_ERROR, f"Some unknown failure connecting to the wifi network: {str(exc)}")

            self.__log(LOG_INFO, "Starting access point...") 
            self.startAccessPoint()
            self.credentials = self.getCredentials()

    @property            
    def connectedToWifi(self):
        return (self.__wifi_connection.active() 
                and self.__wifi_connection.isconnected())

    @property 
    def accessPointIsRunning(self):
        return self.__adhoc_ap.active()
    
    @property
    def connectionState(self):
        return self.__connection_state
    
    def clearCredentials(self):
        if self.credentials is None:
            return

        self.credentials.clearFile()
        self.credentials = None

    def getCredentials(self):
        if not self.accessPointIsRunning:
            self.startAccessPoint()

        credentials = WifiCredentialsServer(port=self.credentials_page_server_port, log_level=self.log_level).getCredentials()
        credentials.filepath = self.credentials_file
        credentials.save()

        return credentials

    def connectToWifi(self):
        if self.credentials is None:
            raise NoWifiCredentialsException()

        self.__connection_state = STA_CONNECTING
        self.__turnOffAdhoc()
        self.__turnOnWifi()
        
        # Clear any existing connection we might have, otherwise this will fail
        # Disconnect doesn't care if there's no connection when we call it, so that's good
        self.__wifi_connection.disconnect()

        self.__log(LOG_DEBUG, f"Credentials - SSID: {self.credentials.ssid}; Password: {self.credentials.password}")
        self.__wifi_connection.connect(self.credentials.ssid, self.credentials.password)        
        
        timeout = 0

        while not self.connectedToWifi and timeout < self.connection_timeout:
            # We have to do this here since the status that indicates wrong password will go away shortly
            # after
            if self.__wifi_connection.status() == network.STAT_WRONG_PASSWORD:
                raise IncorrectWifiPasswordException(f"Bad wifi password: {self.credentials.password}")

            timeout += 1
            self.__log(LOG_DEBUG, f"Not connected, sleeping for second #{timeout}")
            time.sleep_ms(1_000)
        
        status = self.__wifi_connection.status()

        if status == network.STAT_GOT_IP:
            self.__connection_state = STA_CONNECTED
            self.__log(LOG_ERROR, f"Connected at ip: {self.__wifi_connection.ifconfig()}")
        # Of course, we also check here in the off chance that this has occurred in the last second of our timeout
        elif status == network.STAT_WRONG_PASSWORD:
            self.__connection_state = STA_DISCONNECTED
            raise IncorrectWifiPasswordException(f"Bad wifi password: {self.credentials.password}")
        else:
            self.__connection_state = STA_DISCONNECTED
            raise UnknownWifiConnectionFailureException(f"Failed to connect; status = {status}")
        
    def startAccessPoint(self):
        self.__turnOffWifi()
        self.__turnOnAdhoc()
        
        self.__connection_state = STA_ACCESSPOINT

        ifconfig = self.__adhoc_ap.ifconfig()
        self.__log(LOG_ERROR, f"Access point active, ifconfig: {ifconfig}")

    def __setWifiConfig(self):
        self.__wifi_connection.ipconfig(dhcp4=True)

    def __setAdhocConfig(self):
        self.__adhoc_ap.config(essid=self.adhoc_ssid, password=self.adhoc_password)
        # Disabled because of a bug in micropython
        # https://github.com/micropython/micropython/issues/17401
        #self.__adhoc_ap.ifconfig(self.adhoc_ifconfig)

    def __turnOnAdhoc(self):
        if self.__adhoc_ap.active():
            return

        self.__adhoc_ap.active(True)
        while not self.__adhoc_ap.active():
            pass

    def __turnOffAdhoc(self):
        if not self.__adhoc_ap.active():
            return

        self.__adhoc_ap.active(False)
        while self.__adhoc_ap.active():
            pass

    def __turnOnWifi(self):
        if self.__wifi_connection.active():
            return

        self.__wifi_connection.active(True)
        while not self.__wifi_connection.active():
            pass

    def __turnOffWifi(self):
        if not self.__wifi_connection.active():
            return

        self.__wifi_connection.disconnect()

        self.__wifi_connection.active(False)
        while self.__wifi_connection.active():
            pass

    def __log(self, level, str):
        if self.log_level >= level:
            print(str)

class IncorrectWifiPasswordException(Exception):
    def __init__(self, message="Wifi password is incorrect"):
        super().__init__(message)

class UnknownWifiConnectionFailureException(Exception):
    def __init__(self, message="Failed to connect to the wifi"):
        super().__init__(message)

class NoWifiCredentialsException(Exception):
    def __init__(self, message="Tried to connect to wifi without passing any credentials"):
        super().__init__(message)

class WifiCredentials:
    def __init__(self, ssid, password, filepath):
        if (ssid is None or ssid == ""):
            raise Exception("ssid cannot be None or empty string")
        if (password is None or password == ""):
            raise Exception("password cannot be None or empty string")

        self.ssid = ssid
        self.password = password
        self.filepath = filepath

    def save(self, filepath=None):
        if filepath is None and self.filepath is None:
            raise Exception("Cannot write credentials if no filepath is present or passed")
        
        destination = filepath if filepath is not None else self.filepath

        try:
            jsonData = self.__toJson()
            file = open(destination, "w")
            file.write(jsonData)
            file.close()

        except Exception as exc:
            raise Exception(f"Could not write credentials at file location {destination}") from exc

    @staticmethod
    def fromFile(path: str):
        try:
            file = open(path)
            data = file.read()
            file.close()

            return WifiCredentials.__fromJson(data, filepath=path)
        except Exception as exc:
            raise Exception(f"Could not read credentials file at location {path}") from exc
        
    def clearFile(self):
        if (self.filepath is None):
            print("Credentials not stored, nothing to clear.")
            return
        
        try:
            # Maybe test if it exists before trying to open it so we're not using an
            # exception-based workflow
            file = open(self.filepath)
            file.close()
        except Exception as exc:
            print(f"Couldn't open file at {self.filepath}, returning...")
            return
        
        try:
            os.remove(self.filepath)
        except Exception as exc:
            raise Exception("Error clearing credentials") from exc

    def __toJson(self):
        return json.dumps({"ssid": self.ssid, "password": self.password})

    @staticmethod
    def __fromJson(jsonString: str, filepath: str):
        parsed = json.loads(jsonString)
        return WifiCredentials(ssid=parsed["ssid"], password=parsed["password"], filepath=filepath)


DEFAULT_RESPONSE_PAGE = """<!DOCTYPE html>
<html>
    <head> <title>Pico Wifi</title> </head>
    <body> <h1>Pico Wifi</h1>
        <p>Hello from Pico W.</p>
        <form action="/" method="POST">
          <div>
            <label for="ssid">SSID:</label>
            <input name="ssid" id="ssid" type="text"/>
          </div>
          <div>
            <label for="password">Password:</label>
            <input name="password" id="password" type="text"/>
          </div>
          <div>
            <input type="submit" value="Connect" />
          </div>
        </form>
    </body>
</html>
"""

ERROR_PAGE = """<!DOCTYPE html>
<html>
  <head><title>Error</title></head>
  <body>
    <h1>Error submitting credentials</h1>
    <p>Press back to try again</p>
    <h2>Error:</h2>
    <p>%CONTENT%</p>
  </body>
</html>"""

class WifiCredentialsServer:
    def __init__(self,
                 port=80,
                 page=DEFAULT_RESPONSE_PAGE,
                 error_page=ERROR_PAGE,
                 log_level=LOG_ERROR):
        self.port = port
        self.page = page
        self.error_page = error_page
        self.log_level = log_level

        self.addr = socket.getaddrinfo("0.0.0.0", port)[0][-1]
        self.socket = socket.socket()

        # EADDRINUSE prevention
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    
    def terminate(self):
        self.socket.close()

    # Get credentials for a wifi network via a webpage that serves a form.
    def getCredentials(self):
        self.socket.bind(self.addr)
        self.socket.listen(1)

        credentials = None

        # This entire situation will eat shit if the HTTP request is malformed.
        while credentials == None:
            self.__log(LOG_INFO, "Listening for HTTP calls...")
            connection, addr = self.socket.accept()
            self.__log(LOG_INFO, f"client connected from {addr}")

            raw_request = connection.recv(1024)
            request = raw_request.decode('utf-8')

            splitRequest = request.split("\r\n\r\n")

            headers = self.__getRequestHeaders(splitRequest[0])
            # Data may be chunked from the browser.  Safari in particular will _always_ send a POST
            # body as a second chunk, which trips us up here.  Thanks for that, Safari.
            body = self.__getRequestBody(connection, headers, splitRequest[1])

            if(headers["method"] == "POST"):
                credentials = self.__parseCredentials(connection, body)
            if(headers["method"] == "GET"):
                self.__respondWithInputPage(connection)

            connection.close()

        self.terminate()
        return WifiCredentials(credentials["ssid"], credentials["password"], None)

    def __getRequestHeaders(self, headerBlock):
        splitHeaders = [header.split(":") for header in headerBlock.split("\r\n")]

        requestLine = splitHeaders[0][0].split()

        headers = {header[0]:header[1] for header in splitHeaders[1:]}

        headers["method"] = requestLine[0]
        headers["path"] = requestLine[1]
        headers["protocol"] = requestLine[2]

        return headers

    # Get the entire body from an HTTP request using the Content-Length header's value
    # Final argument is any body data that was received alongside the headers
    def __getRequestBody(self, connection, headers, requestBody):
        contentLength = int(headers["Content-Length"]) if "Content-Length" in headers else 0
        body = requestBody

        # This fails if we ever get characters that are wider than 1 byte, but surely that's fine
        # Wifi networks are only administered and authenticated in English, right?
        while len(body) < contentLength:
            moreData = connection.recv(1024)
            body += moreData.decode("utf-8")

        return body

    # Decode x-www-form-urlencoded data that is present on the POST body
    # This probably works, except when it doesn't
    def __urlDecode(self, toDecode):
        toDecode.replace("+", " ")

        chars = []
        i = 0
        while i < len(toDecode):
            if toDecode[i] == "%" and i + 2 < len(toDecode):
                hex = toDecode[i+1:i+3]
                try:
                    char = chr(int(hex, 16))
                    chars.append(char)
                    i += 3
                except ValueError:
                    chars.append(toDecode[i])
                    i += 1
            else:
                chars.append(toDecode[i])
                i += 1

        return "".join(chars)

    def __respondWithInputPage(self, connection):
        connection.send("HTTP/1.0 200 OK\r\nContent-type: text/html\r\n\r\n")
        connection.send(self.page)

    # Parses out a set of credentials from the HTTP POST request body
    # Expects a form-encoded utf-8 string
    def __parseCredentials(self, connection, postBody):
        if postBody == "" or postBody is None:
            self.__sendBadRequest(connection, "Password and SSID cannot be empty")
            return None
        
        splitParams = [param.split("=") for param in postBody.split("&")]
        params = {self.__urlDecode(param[0]): self.__urlDecode(param[1]) for param in splitParams}
        self.__log(LOG_DEBUG, f"parsed form data: {params}")

        if "password" not in params or "ssid" not in params:
            self.__log(LOG_ERROR, "Didn't get the right params, page problem!")
            self.__sendBadRequest(connection, "Missing either password or ssid query param in submisssion")
            return None
        if params["password"] == "":
            self.__sendBadRequest(connection, "Password cannot be empty")
            return None
        if params["ssid"] == "":
            self.__sendBadRequest(connection, "SSID cannot be empty")
            return None

        connection.send("HTTP/1.0 200 OK\r\nContent-type: text/html\r\n\r\n")
        return params
    
    def __sendBadRequest(self, connection, errorMessage=None):
        page = self.error_page.replace("%CONTENT%", errorMessage) if errorMessage is not None else ""
        lengthHeader = f"\r\nContent-Length:{len(page)}" if errorMessage is not None else ""

        connection.send(f"HTTP/1.0 400 Bad Request\r\nContent-type: text/html; charset=\"utf-8\"{lengthHeader}\r\n\r\n{page}")
    
    def __log(self, level, str):
        if self.log_level >= level:
            print(str)

# Testing
"""
if __name__ == "__main__":
    wifi = PicoWifi()
    wifi.clearCredentials()
    wifi.init()
"""
