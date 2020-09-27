# Overview

- My infrastructure as code using [Docker](https://www.docker.com/) containers &amp; [docker-compose](https://docs.docker.com/compose/).
- This repository's goal is to provide assistance and guidance into the configuration of different services around home automation using compose.

## Configuration Sections

### Admin

Here you can find services I use mainly for administering my infrastructure:

1. [Cloud9](https://github.com/c9) - A compact web-based IDE I use daily to edit my different code and configurations.
1. [Prune](https://github.com/liske/docker-prune) - A container used to do dome maintenance around docker objects such as images, unused volumes, etc.
1. [Ouroboros](https://github.com/pyouroboros/ouroboros) - Auto-updater for docker containers.
1. [Portainer](https://www.portainer.io/) - Simple yet powerful web-based container manager.

### Hass

Services used for my [HomeAssistant](https://www.home-assistant.io/), my home automation hub of choice.

1. [MariaDB](https://mariadb.org/) - An open source relational database, used as the data store for home assistant's data.
1. [Mosquitto](https://mosquitto.org/) - An open source MQTT broker used as a pub-sub server for many of my devices.
1. [HomeAssistant](https://www.home-assistant.io/) - An open source home automation hub.
1. [MotionEye](https://github.com/ccrisan/motioneye) - A service to gather and control cctv cameras.

### Media

All media-related services used to manage my media library.

1. [SickChill](https://github.com/SickChill/SickChill) - Used to automatically download torrents and their metadata.
1. [Transmission](https://transmissionbt.com/) - A simple bittorrent client.

### Network

All services related to external access to the different services I run are listed here.

1. [NGINX](https://hub.docker.com/r/linuxserver/letsencrypt) - A powerful reverse proxy for securely exposing public services. This container also takes care of the renewal of the DuckDNS SSL certificate.
1. [DuckDNS](https://www.duckdns.org/) - A free dynamic DNS hosted on AWS. Used to update my public IP address with my registered domain.

### NextCloud

A dropbox-like service used to synchronize local files with mobile devices.

1. [MariaDB](https://mariadb.org/) - An open source relational database, used as the data store for NextCloud's data.
1. [NextCloud](https://nextcloud.com/) - A file-synchronization and collaboration service.

### Traccar

A service used to report location data locally without hosting it on any external service.

1. [MariaDB](https://mariadb.org/) - An open source relational database, used as the data store for Traccar's data.
1. [Traccar](https://www.traccar.org/) - Traccar is the leading GPS tracking software. Vehicle and personal tracking. Self hosting and cloud-based solution. Real time view, reports, notifications.
