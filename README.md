# bo

IN-PROGRESS

Utilite for sync files (like rsync) and run build on remote server (or Virtual Machine in local network)

```
Usage:
    'bo config init' - add current directory to config
    'bo config deinit' - remove current directory from config
    'bo config ls' - print configs
    'bo config path' - path to config file
    'bo sync' - partial sync to remote server
    'bo server' - partial sync to remote server
```


## Install (First way)

Ubuntu 24.04:
```sh
$ python3 -m pip install --break-system-packages pyyaml
$ sudo wget https://raw.githubusercontent.com/sea5kg/bo/refs/heads/dev/bo.py /usr/bin/bo && sudo chmod +x /usr/bin/bo
```

## Install (Second way)

Linux
```sh
$ python3 -m pip install --break-system-packages pyyaml
$ git clone https://github.com/sea5kg/bo.git ~/bo.git
$ sudo ln -s ~/bo.git /usr/bin/bo
```

## How to use

### Run bo server

1. Install bo on target virtual machine
2. Start `bo server` or `python -u bo.py server`

### Configure project sync on current machine

On host mchine init new target for directory:
```
$ cd your-project.git
$ bo config init
Welcom to bo (v0.0.1)!
Utilite for sync files (like rsync) and run build on remote server (or Virtual Machine in local network)

Server: 192.168.5.30
Target dir: C:\develop\your_project111
Done.
```

### Configure  stack of commands on current machine

```
$ cd your-project.git
$ bo config command
```


### Sync files with remote machine

```
$ cd your-project.git
$ bo sync
```

### Sync files with remote machine

```
$ cd your-project.git
$ bo run
```
