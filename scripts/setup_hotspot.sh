#!/bin/bash

sudo nmcli device wifi hotspot ifname wlan0 ssid TheraView_$(hostname) password ritaengs &

# Give NetworkManager time to create the "Hotspot" connection
sleep 5

sudo nmcli connection modify Hotspot connection.autoconnect yes
