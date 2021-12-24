# ha-toyota-na

## Introduction
This is a experimental Home Assistant integration for Toyota North America.

## Installation
1. Download this repo by either of the following method
- `git clone https://github.com/widewing/ha-toyota-na`
- Download https://github.com/widewing/ha-toyota-na/archive/refs/heads/master.zip
2. Copy or link this repo into Home Assistant "custome_components" directory
- `ln -s ha-toyota-na/custom_components/toyota_na ~/.homeassistant/custom_components/`

## Configuration
Click "Add integration" from Home Assistant, search "Toyota (North America)", click to add.

It will ask for `authorization_code`. Follow https://github.com/widewing/toyota-na to get the code.

## Limitations
Currently it need the companion desktop application (https://github.com/widewing/toyota-na) to complete the login process.

The OAuth2 session will expire in 30 minutes but the integration will automatically renew every 5 minutes.
However it's not guarenteed to always keep the session available, it will need to be reconfigured in a random time from several hours to several days.


## Credits
Thanks @DurgNomis-drol for making the the original [Toyota Integration](https://github.com/DurgNomis-drol/ha_toyota) and for providing many suggestions.
