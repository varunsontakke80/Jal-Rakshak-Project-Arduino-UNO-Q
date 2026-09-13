"""
Jal Rakshak Pipe Node — Configuration.

The Pipe Node has NO internet connection and does NOT push to Firebase.
All telemetry is transmitted via LoRa to the Master Node.
The Master Node handles all cloud (Firebase) uploads.

Node identity can be configured here.
"""

# Node identity — change this value per physical node deployment (1, 2, 3 or 4)
NODE_ID = 1

# Wi-Fi is managed by the Dragonwing Linux OS (nmcli).
# The Pipe Node hosts its own Wi-Fi access point or joins a local network
# so field technicians can connect and access the diagnostic WebUI on port 7000.