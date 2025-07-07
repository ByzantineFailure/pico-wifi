import os
import socket
import network
import ujson as json
import sys
import time

DEFAULT_CREDENTIAL_LOCATION = "wifi.json"
DEFAULT_CONNECTION_TIMEOUT_SECONDS = 30

DEFAULT_ADHOC_SSID = "PicoWifi Adhoc"
DEFAULT_ADHOC_PASSWORD = "1234567890"
DEFAULT_ADHOC_IFCONFIG = ("192.168.1.1", "255.255.255.0", "192.168.1.1", "8.8.8.8")

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


# Status values for the network state
STA_DISCONNECTED = 1
STA_CONNECTING = 2
STA_CONNECTED = 3
STA_ADHOC = 4

# Must be a singleton since it has access to the network hardware
class PicoWifi:
    def __init__(self,
                 credentials_file=DEFAULT_CREDENTIAL_LOCATION,
                 connection_timeout=DEFAULT_CONNECTION_TIMEOUT_SECONDS,
                 adhoc_ifconfig=DEFAULT_ADHOC_IFCONFIG,
                 adhoc_ssid=DEFAULT_ADHOC_SSID,
                 adhoc_password=DEFAULT_ADHOC_PASSWORD,
                 credentials_page_server_port=80):
        try:
            self.credentials = WifiCredentials.fromFile(credentials_file)
        except Exception:
            print("Cannot open credentials file, will start in ad-hoc mode")
            self.credentials = None
       
        self.credentials_file = credentials_file

        self.adhoc_ifconfig = adhoc_ifconfig
        self.adhoc_ssid = adhoc_ssid
        self.adhoc_password = adhoc_password
        self.connection_timeout = connection_timeout
        self.credentials_page_server_port = credentials_page_server_port

        self.connection_state = STA_DISCONNECTED

        self.adhoc_ap = network.WLAN(network.AP_IF)
        self.wifi_connection = network.WLAN(network.STA_IF)

        self.__setWifiConfig()
        self.__setAdhocConfig()

    def init(self):
        if (self.credentials is not None):
            try:
                self.__connectToWifi()
                return
            except Exception as exc:
                sys.print_exception(exc)
                print("Could not connect to wifi, standing up adhoc mode...")
        self.__setupAdhoc()

        self.credentials = self.getCredentials()
        print("Connecting to wifi...")
        self.__connectToWifi()
        print("Connected!")
    
    def connectedToWifi(self):
        return self.wifi_connection.isconnected()

    def clearCredentials(self):
        if self.credentials is None:
            return

        self.credentials.clearFile()
        self.credentials = None

    def getCredentials(self):
        if self.credentials is not None:
            return self.credentials.clearFile()

        if not self.adhoc_ap.active():
            self.__turnOffWifi()
            self.__turnOnAdhoc()
        
        credentials = WifiCredentialsPage(port=self.credentials_page_server_port).getCredentials()
        credentials.filepath = self.credentials_file
        credentials.save()

        return credentials

    def __connectToWifi(self):
        if self.credentials is None:
            raise Exception("Attempted to connect to wifi without credentials")

        self.connection_state = STA_CONNECTING
        self.__turnOffAdhoc()
        self.__turnOnWifi()
        
        # Clear any existing connection we might have, otherwise this will fail
        # Disconnect doesn't care if there's no connection when we call it, so that's good
        self.wifi_connection.disconnect()

        print(f"Credentials - SSID: {self.credentials.ssid}; Password: {self.credentials.password}")
        self.wifi_connection.connect(self.credentials.ssid, self.credentials.password)        
        
        timeout = 0
        while timeout < self.connection_timeout:
            # If we increment timeout within the if statement after the sleep, the Pico W hangs
            # Increment it here instead.  ...idk, man
            timeout += 1
            if self.wifi_connection.isconnected() == False:
                print(f"Not connected, sleeping for second #{timeout}")
                time.sleep_ms(1_000)
        
        if self.wifi_connection.isconnected() == False:
            raise Exception("Wifi connection timed out")
        
        status = self.wifi_connection.status()
        
        if status == network.STAT_GOT_IP:
            self.connection_state = STA_CONNECTED
            print(f"Connected at ip: {self.wifi_connection.ifconfig()}")
        elif status == network.STAT_WRONG_PASSWORD:
            self.connection_state = STA_DISCONNECTED
            raise Exception("Bad wifi password")
        else:
            self.connection_state = STA_DISCONNECTED
            raise Exception(f"Failed to connect; status = {status}")
        

    def __setupAdhoc(self):
        self.connection_state = STA_ADHOC

        self.__turnOffWifi()
        self.__turnOnAdhoc()

        ifconfig = self.adhoc_ap.ifconfig()
        print(f"adhoc active, ifconfig: {ifconfig}")

    def __setWifiConfig(self):
        self.wifi_connection.ipconfig(dhcp4=True)

    def __setAdhocConfig(self):
        self.adhoc_ap.config(essid=self.adhoc_ssid, password=self.adhoc_password)
        #self.adhoc_ap.ifconfig(self.adhoc_ifconfig)

    def __turnOnAdhoc(self):
        if self.adhoc_ap.active():
            return

        self.adhoc_ap.active(True)
        while not self.adhoc_ap.active():
            pass
        print("Adhoc active")

    def __turnOffAdhoc(self):
        if not self.adhoc_ap.active():
            return

        self.adhoc_ap.active(False)
        while self.adhoc_ap.active():
            pass

    def __turnOnWifi(self):
        if self.wifi_connection.active():
            return

        self.wifi_connection.active(True)
        while not self.wifi_connection.active():
            pass

    def __turnOffWifi(self):
        if not self.wifi_connection.active():
            return

        self.wifi_connection.disconnect()

        self.wifi_connection.active(False)
        while self.wifi_connection.active():
            pass

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

class WifiCredentialsPage:
    def __init__(self,
                 port=80,
                 page=DEFAULT_RESPONSE_PAGE,
                 error_page=ERROR_PAGE):
        self.port = port
        self.page = page
        self.error_page = error_page

        self.addr = socket.getaddrinfo("0.0.0.0", port)[0][-1]
        self.socket = socket.socket()

        # EADDRINUSE prevention
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    
    def terminate(self):
        self.socket.close()

    # This entire situation will eat shit if the request is malformed.
    def getCredentials(self):
        self.socket.bind(self.addr)
        self.socket.listen(1)

        credentials = None

        while credentials == None:
            print("Listening for HTTP calls...")
            connection, addr = self.socket.accept()
            print("client connected from", addr)
            raw_request = connection.recv(1024)
            request = raw_request.decode('utf-8')

            splitRequest = request.split("\r\n\r\n")
            splitHeaders = [header.split(":") for header in splitRequest[0].split("\r\n")]

            preamble = splitHeaders[0][0].split()

            print(f"splitHeaders: {splitHeaders}")
            headers = {header[0]:header[1] for header in splitHeaders[1:]}

            headers["Method"] = preamble[0]
            headers["Path"] = preamble[1]
            headers["Protocol"] = preamble[2]

            # Data may be chunked from the browser.  Safari in particular will _always_ send a POST
            # body as a second chunk, which trips us up here 
            contentLength = int(headers["Content-Length"]) if "Content-Length" in headers else 0
            body = self.__getRequestBody(connection, contentLength, splitRequest[1])

            method = headers["Method"]
            path = headers["Path"]

            print(f"Method: '{method}'\nPath: '{path}'\nBody: '{body}'")

            if(method == "POST"):
                credentials = self.__parseCredentials(connection, body)
            if(method == "GET"):
                self.__respondWithInputPage(connection)

            connection.close()

        return WifiCredentials(credentials["ssid"], credentials["password"], None)
    
    def __getRequestBody(self, connection, contentLength, requestBody):
        body = requestBody

        # This fails if we ever get characters that are wider than 1 byte, but surely that's fine
        # Wifi networks are only used by English-speaking people, right?
        while len(body) < contentLength:
            moreData = connection.recv(1024)
            body += moreData.decode("utf-8")

        return body

    # This probably works, mostly
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

    def __parseCredentials(self, connection, formParams):
        if formParams == "" or formParams is None:
            self.__sendBadRequest(connection, "Password and SSID cannot be empty")
            return None
        
        splitParams = [param.split("=") for param in formParams.split("&")]
        params = {self.__urlDecode(param[0]): self.__urlDecode(param[1]) for param in splitParams}
        print(f"parsed form data: {params}")

        if "password" not in params or "ssid" not in params:
            print("Didn't get the right params, page problem!")
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

wifi = PicoWifi()
wifi.init()
