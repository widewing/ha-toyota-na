# ha-toyota-na

## Introduction
This is a Home Assistant integration for Toyota North America.

## Stable
![GitHub release (latest by date)](https://img.shields.io/github/v/release/widewing/ha-toyota-na?style=for-the-badge) ![GitHub Release Date](https://img.shields.io/github/release-date/widewing/ha-toyota-na?style=for-the-badge) ![GitHub Releases](https://img.shields.io/github/downloads/widewing/ha-toyota-na/latest/total?color=purple&label=%20release%20Downloads&style=for-the-badge) 

## Current features
Certain entities and services require the Remote Subscription.

Sensors:
* Door lock status (Remote Subscription Required)
* Window/Moonroof status (Remote Subscription Required)
* Trunk Status (Remote Subscription Required)
* Real time location (Remote Subscription Required)
* Last Parked Location
* Tire Pressure
* Fuel Level
* Odometer
* Oil Status
* Key Fob Battery Status
* Last Update
* Last Tire Pressure Update
* Speed
* EV Plug Status
* EV Remaining Charge Time
* EV Travel Distance
* EV Charge Type
* EV Charge Start Time
* EV Charge End Time
* EV Connector Status
* EV Charging Status

Services:
* Lock/Unlock Doors (Remote Subscription Required)
* Remote Start/Stop Engine (Remote Subscription Required)
* Hazards On/Off (Remote Subscription Required)
* Refresh Data
## Installation
### HACS
1. Install HACS: https://hacs.xyz/docs/setup/download
2. Search and install "Toyota (North America)" in HACS integration store

### Manual installation:
1. Download this repo by either of the following method
- `git clone https://github.com/widewing/ha-toyota-na`
- Download https://github.com/widewing/ha-toyota-na/archive/refs/heads/master.zip
2. Copy or link this repo into Home Assistant "custome_components" directory
- `ln -s ha-toyota-na/custom_components/toyota_na ~/.homeassistant/custom_components/`

## Configuration
Click "Add integration" from Home Assistant, search "Toyota (North America)", click to add.

Enter your username and password, and then OTP for Toyota One App or Toyota Entune App and all set.

After setting up, Most information in Toyota One app should be available in Home Assistant.
![image](https://user-images.githubusercontent.com/4755389/147372481-4d280b6e-6f61-434c-a768-f4a089f009c3.png)

## Credits
Thanks @DurgNomis-drol for making the original [Toyota Integration](https://github.com/DurgNomis-drol/ha_toyota) and bringing up the discussion thread at https://github.com/DurgNomis-drol/mytoyota/issues/7.

Thanks @visualage for finding the way to authenticate headlessly.
