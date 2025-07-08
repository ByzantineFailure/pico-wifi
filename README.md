# pico-wifi
Small MicroPython library to help a Raspberry Pi Pico W connect to the internet in a user-friendly way.

Tested and running on a Raspberry Pi Pico W.  May work on a Pico 2 W, entirely untested.

## Basic Usage
```
import pico_wifi

wifi = pico_wifi.PicoWifi()
wifi.init()
```
Connect to the wifi network that it stands up.  By default the SSID is `PicoWifi Adhoc` and the password is `1234567890`).

Open a browser and navigate via `http` to the IP that has been assigned to the Pico - this is the first value in the tuple that is printed to the console (mine defaults to `192.168.4.1`, so the address is `http://192.168.4.1`).  This will display the credentials page.  Enter your credentials and hit "connect" to connect to the network you've specified.

**CONNECTING VIA `https://` WILL NOT WORK.**  Most browsers will try to do this automatically, so make sure you've added the `http://` explicitly.

If there is some error connecting, it should be printed out to the console.

Advanced users who want control of how their connection is set up may use the methods and parameters exposed on any of the classes below.

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
| `log_level` | `LOG_ERROR` | Verbosity of logging.  See possible values below.  If you're having problems, consider setting this to `LOG_INFO` or `LOG_DEBUG` to see more information |
| `adhoc_ifconfig` | `None` | **CURRENTLY NON-FUNCTIONAL** Parameters for `ifconfig` called on the AP.  Used to set IP, subnet, etc. |

#### Properties

All constructor parameters are accessible as properties.  Others are documented here:

| Property | Description |
| -------- | ----------- |
| `connectedToWifi` | If the Pico W is currently connected to a wifi network |
| `accessPointIsRunning` | If the Pico W is currently in AP mode |
| `credentials` | A `WifiCredentials` instance used to connect to the internet.  `getCredentials()` will set this after it gets them from the user.|
| `connectionState` | What the status of the connection is at any given point.  Valid values below |

Values for `connectionState` are:
* `pico_wifi.STA_DISCONNECTED`: Not connected to wifi, and the AP is not running
* `pico_wifi.STA_CONNECTING`: Currently attempting to connect to a wifi network
* `pico_wifi.STA_CONNECTED`: Connected to a wifi network
* `pico_wifi.STA_ACCESSPOINT`: Running in AP mode

#### `PicoWifi.init()`

Top-level, basic call that strings together all other available class methods to make setting up wifi easy.

In a `while True` loop, this will:
* Call `connectToWifi()`.  If this succeeds, break from the loop and return
* If this fails, call `startAccessPoint()` and fetch credentials for the next connection attempt via `getCredentials()`
* Go back to the beginning

```python
wifi = PicoWifi()
wifi.init()
```

#### `PicoWifi.connectToWifi()`

Attempt to connect to the wifi using the credentials present on the instance.

* Turns off the access point if it is running
* Turns on the wifi connection if it is not running
* Checks if a `WifiCredentials` instance is present in the `credentials` property.  If there is none, throws a `NoWifiCredentialsException`
* Attempts to connect to the wifi network with the values within `credentials`
  * If the password is wrong, throws an `IncorrectWifiPasswordException`
  * If there is no AP serving the SSID, throws a `NoAccessPointFoundException`
  * If the connection times out or fails for some other reason, throws an `UnknownWifiConnectionFailureException` with the status code from the underlying connection in the message
  * If the connection is formed successfully, returns

Example:
```python
wifi = PicoWifi()
if wifi.credentials is None:
    wifi.getCredentials()
wifi.connectToWifi()
```

#### `PicoWifi.startAccessPoint()`

Turns on the Pico W's wifi in access point mode and stands up an adhoc network using the parameters provided in the constructor.

* Turns off the wifi connection, if it is active
* Turns on the access point if it is not running

#### `PicoWifi.getCredentials()`

Single call to get credentials from the user via a webpage served on an adhoc network.

* Turns off the wifi connection, if it is active.
* Turns on the access point if it is not running.
* Instantiates a `WifiCredentialsServer` which listens on `credentials_page_server_port` (see constructor params).
* Calls `getCredentials()` on the `WifiCredentialsServer` instance.
* Writes the resulting `WifiCredentials` to the `credentials` property
* Returns the value of the `credentials` property

#### `PicoWifi.clearCredentials()`

Clears any stored credentials.  This is useful when attempting to debug or remove known-bad credentials that are stored in flash.

* Deletes any existing credentials file at the path stored in the `credentials_file` property
* Sets `credentials` to `None`

### WifiCredentialsServer

Class that stands up a small web server responsible for getting wifi credentials from the user.

#### ConstructorParameters

| Parameter | Default | Description |
| --------- | ------- | ----------- |
| `port`    | `80`    | The port the webserver should listen on.  Defaults to 80 (HTTP default port) |
| `page`    | `"<html>...elided...</html>"` | A string which contains an HTML page to return when GET is called at any path on the server. |
| `error_page` | `"<html>...elided...</html>"` | A string which contains an HTML page to return when an error occurs during form submission |
| `log_level` | `LOG_ERROR` | Verbosity of logging.  See possible values below. |

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

### Log Levels

Logs are available at different granularities.  They will be printed to console depending upon the `log_level` value of classes that support it.

* `LOG_NONE` - Log nothing at all to console.  Silent.
* `LOG_ERROR` - Log only errors and high-importance messages like the ip of the device.  Default value.
* `LOG_INFO` - Log events of interest without significant detail.  Recommended debugging mode for users.
* `LOG_DEBUG` - Log everything to assist with debugging.  Highly-verbose, intended for debugging the library.  May be useful if you're writing your own form submission page or error page.

### Exceptions

* `NoWifiCredentialsException` - Exception thrown if an attempt to connect to a wifi network is made before credentials are set.
* `UnknownWifiConnectionFailureException` - Exception thrown if connecting to a wifi network fails for a reason the library does not explicitly handle.
* `IncorrectWifiPasswordException` - Exception thrown if the wifi password is incorrect.
* `NoAccessPointFoundException` - Exception thrown if attempting to connect to an SSID that the wifi device cannot find

## Troubleshooting

Things I came across when building this, and general notes:

* If your `adhoc_password` is less than 8 chars, it won't meet the minimum required for WPA auth and your AP won't work
* My Pico W seemed unable to connect to a 5 GHz wifi network.  2.4 GHz worked just fine.
* If you're having trouble determining what's up, try setting the `log_level` parameter to `pico_wifi.LOG_DEBUG` to get more information.
* After a successful connnection to a network, the Pico will not actually accept new credentials for that same network.  You'll have to remove power from the device to get it to accept new credentials.
* There is a mysterious status that can be returned from `status()` on the WLAN interface with a value of `2`.  This is between `network.STAT_CONNECTING` and `network.STAT_GOT_IP`.  This library handles this case, but uh... watch out for that.
* `ifconfig()` straight-up doesn't work in AP mode: https://github.com/micropython/micropython/issues/17401
* This project involved building a minimally-featured HTTP server from scratch.  There may be bugs with non-ASCII characters used in SSIDs and passwords.  Please feel free to report an issue on this repo with a repro case that includes your SSID+Password, or at least the characters that are causing a problem.  (I know, credentials on the open web, sorry :( )

## TODOs

* Get `ifconfig` parameters for AP mode working.  Setting a consistent IP is important
  * Blocked on https://github.com/micropython/micropython/issues/17401
* Write up a guide on how to use `asyncio` to multithread this
* Any kind of testing.  At all. 

## Author's Notes

This library was built to help my husband out on a personal project.  You're welcome to use it, I'm open to PRs and external contributions, and may even try to resolve issues depending upon how much time I have on my hands.

However, if it doesn't meet your needs, I encourage you to fork it!  My time is limited and the odds of me adding any features that aren't relevant to our project(s) are... low.  I'd love to accept any contributions folks may have, though!

I've done my best to make the simple webpage accessible using semantic HTML and some basic CSS-based focus indicators.  If you have an a11y-focused issue with the credentials page, please file it and I'll do my best to fix it ASAP.

And finally, a reminder to myself: [It's okay for your open-source library to be a bit shitty](https://www.drmaciver.com/2015/04/its-ok-for-your-open-source-library-to-be-a-bit-shitty/)