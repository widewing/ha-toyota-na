# ha-toyota-na

## Introduction
This is a Home Assistant integration for Toyota North America.

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

Enter your username and password for Toyota One App or Toyota Entune App and all set.

After setting up, Most information in Toyota One app should be available in Home Assistant.
![image](https://user-images.githubusercontent.com/4755389/147372481-4d280b6e-6f61-434c-a768-f4a089f009c3.png)

## Discord
https://discord.gg/mFHJYew658

## Credits
Thanks @DurgNomis-drol for making the the original [Toyota Integration](https://github.com/DurgNomis-drol/ha_toyota) and bringing up the discussion thread at https://github.com/DurgNomis-drol/mytoyota/issues/7.

Thanks @visualage for finding the way to authenticate headlessly.
