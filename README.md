# pico-wifi
Small MicroPython library to help a Raspberry Pi Pico W connect to the internet in a user-friendly way.

Tested and running on a Raspberry Pi Pico W.  May work on a Pico 2 W, entirely untested.

## Usage
```
import pico_wifi

wifi = pico_wifi.PicoWifi()
wifi.init()
```

Connect to the IP that is printed to the console (first value in the tuple, mine defaults to `192.168.4.1`) via http to see the credentials page.

Advanced users who want control of how their connection is set up may use the methods exposed on any of the classes below.

## API

### PicoWifi

Top-level class that orchestrates network connectivity

#### Constructor Parameters

It is recommended to use named parameters when constructing an instance and let the defaults handle the rest.

| Parameter | Default | Description |
| --------- | ------- | ----------- |
| `credentials_file` | `"wifi.json"` | A location within the Micropython filesystem to look for and store wifi credentials.|
| `connection_timeout` | `30` | How many seconds to wait before declaring the connection failed, if the network interface does not do it for us.  Setting this value too low may prevent the library from accurately detecting if the wifi password is wrong.|
| `adhoc_ssid` | `"PicoWifi Adhoc"`| SSID for the adhoc network. |
| `adhoc_password` | `"1234567890"` | Password for the adhoc network. A password that is too short may cause all auth to fail! |
| `credentials_page_server_port` | `80` | Port to run the credentials HTTP Server on. |
| `adhoc_ifconfig` | `None` | **CURRENTLY NON-FUNCTIONAL** Parameters for `ifconfig` called on the AP.  Used to set IP, subnet, etc. |

#### Properties

All constructor parameters are accessible as properties.  Others are documented here:

| Property | Description |
| -------- | ----------- |
| `connectedToWifi` | If the Pico W is currently connected to a wifi network |
| `accessPointIsRunning` | If the Pico W is currently in AP mode |
| `credentials` | A `WifiCredentials` instance used to connect to the internet.  Prefer using `getCredentials()` to set this instead of setting it manually.|
| `connectionState` | What the status of the connection is at any given point.  Valid values below |

Values for `connectionState` are:
* `pico_wifi.STA_DISCONNECTED`: Not connected to wifi, and the AP is not running
* `pico_wifi.STA_CONNECTING`: Currently attempting to connect to a wifi network
* `pico_wifi.STA_CONNECTED`: Connected to a wifi network
* `pico_wifi.STA_ACCESSPOINT`: Running in AP mode

#### `PicoWifi.init()`

Top-level, basic call that strings together all other available class methods to make setting up wifi easy.

In a `while True` loop, this will:
* Call `connectToWifi()`
* If this fails, call `startAccessPoint()` and fetch credentials for the next connection attempt via `getCredentials()`
* Go back to the beginning

```python
wifi = PicoWifi()
wifi.init()
```

#### `PicoWifi.connectToWifi()`

Attempt to connect to the wifi using the credentials present on the instance.  If no credentials are present (e.g. if `credentials_file` was not present and `getCredentials()` was not called), this method will throw a `NoWifiCredentialsException`.

If the wifi connection fails due to a bad password, this method will throw a `IncorrectWifiPasswordException`.

If the wifi connection fails for any other reason, this method will throw an `UnknownWifiConnectionFailureException`.  The status code from the underlying `network` library will be present in the exception's message.

Example:
```python
wifi = PicoWifi()
if wifi.credentials is None:
    wifi.getCredentials()
wifi.connectToWifi()
```

#### `PicoWifi.startAccessPoint()`

Turns on the Pico W's wifi in access point mode and stands up an adhoc network using the parameters provided in the constructor.

#### `PicoWifi.getCredentials()`

Turns on the wifi controller's `AP_IF` interface if it's not already running, and instantiates a `WifiCredentialsServer` which listens on `credentials_page_server_port` (see constructor params).

Writes the resulting `WifiCredentials` instance to `credentials_file` in flash memory, then returns it.

#### `PicoWifi.clearCredentials()`

Deletes any existing credentials from flash memory and clears any credentials set on the instance of `PicoWifi`.

This is useful when attempting to debug or remove known-bad credentials that are stored in flash.

### WifiCredentialsServer

Class that stands up a small web server responsible for getting wifi credentials from the user.

#### ConstructorParameters

| Parameter | Default | Description |
| --------- | ------- | ----------- |
| `port`    | `80`    | The port the webserver should listen on.  Defaults to 80 (HTTP default port) |
| `page`    | `"<html>...elided...</html>"` | A string which contains an HTML page to return when GET is called at any path on the server. |
| `error_page` | `"<html>...elided...</html>"` | A string which contains an HTML page to return when an error occurs during form submission |

#### `WifiCredentialsServer.getCredentials()`

Starts a web server that listes on `port`.

`GET` to any path will return `page`.

`POST` to any path will parse out the request body looking for `x-www-form-urlencoded` data and pulling out values for `ssid` and `password`.  If these values are not present or are empty, the server will return a `400`.  The body of the response will be `error_page` with any instance of `%CONTENT%` replaced by a human-readable error message.

If the values sent to `POST` are valid, the server will shut down and this method will return an instance of `WifiCredentials` that contains them.

#### `WifiCredentialsServer.terminate()`

Tears down any running server and associated sockets and resources.

### WifiCredentials

Class that encapsulates wifi credentials and can read+write them to/from flash.

#### Constructor Parameters

No defaults are defined for any of these parameters.

| Parameter | Description |
| --------- | ----------- |
| `ssid`    | SSID of the network to connect to |
| `password` | Plaintext password of the network to connect to |
| `filepath` | Path to store the credentials at in flash.  `None` is a valid value if this instance is not intended to be written to flash memory. |

#### `WifiCredentials.save(filepath=None)`

Saves the instance to flash memory at the location of the argument `filepath`.  If the argument `filepath` is not defined, uses the value of `self.filepath` (which was passed in the constructor).  If neither is defined, throws an `Exception`.

```python
credentials = WifiCredentials(ssid="ssid", password="password", filepath="wifi.json")
credentials.save()
```

#### `WifiCredentials.clearFile()`

Deletes any data in flash memory at `self.filepath`.

```python
credentials = WifiCredentials(ssid="ssid", password="password", filepath="wifi.json")
credentials.clearFile()
```

#### `WifiCredentials.fromFile(path)` (Static)

Reads the file at `path` and constructs an instance of `WifiCredentials` from it.

```python
credentials = WifiCredentials.fromFile("wifi.json")
```

### Exceptions

* `NoWifiCredentialsException` - Exception thrown if an attempt to connect to a wifi network is made before credentials are set.
* `UnknownWifiConnectionFailureException` - Exception thrown if connecting to a wifi network fails for a reason the library does not explicitly handle.
* `IncorrectWifiPasswordException` - Exception thrown if the wifi password is incorrect.

## Author's Notes

This library was built to help my husband out on a personal project.  You're welcome to use it, I'm open to PRs and external contributions, and may even try to resolve issues depending upon how much time I have on my hands.

However, if it doesn't meet your needs, I encourage you to fork it!  My time is limited I'd love to accept any contributions folks may have, but my time is limited and odds of me adding features are reasonably low.
