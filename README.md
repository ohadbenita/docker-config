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

### Network

### NextCloud

### Traccar
