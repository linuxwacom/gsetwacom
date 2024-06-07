# gsetwacom

**This is pre-alpha software, it's merely a PoC right now**

gsetwacom is a commandline utility that changes tablet configuration in
GNOME. It provides a CLI around the GSettings schemas that allows.

The name is a reference to the xsetwacom tool that provided a similar CLI
for the [xf86-input-wacom Xorg driver](https://github.com/linuxwacom/xf86-input-wacom).

-----

**Table of Contents**

- [Installation](#installation)
- [Usage](#usage)
- [Limitations](#notes)
- [License](#license)

## Installation

```console
pip install git+https://github.com/whot/gsetwacom
```

## Usage

`gsetwacom` splits its commands into a `tablet` and `stylus` group, commands typically
follow this invocation:
```
$ gsetwacom tablet $tablet-vid-pid <subcommand>
$ gsetwacom stylus $stylus-serial <subcommand>
```
Where identifier is the vid/pid of the tablet or the serial of the stylus.
For details on any command see `gsetwacom --help` or `gsetwacom <command> --help`.

Examples for tablet configuration:
```
$ gsetwacom list-tablets
devices:
- name: "HUION Huion Tablet_H641P Pen"
  usbid: "256C:0066"
- name: "Wacom Intuos Pro M Pen"
  usbid: "056A:0357"

$ gsetwacom tablet "056A:0357" show
area=[0.0, 0.0, 0.0, 0.0]
keep-aspect=true
left-handed=false
mapping='absolute'
output=['GSM', 'LG HDR 4K', '308NTXRBZ298', 'DP-1']

$ gsetwacom tablet "056A:0357" set-left-handed true

$ gsetwacom tablet "056A:0357" set-button-action A keybinding "<Control><Alt>t"
$ gsetwacom tablet "056A:0357" set-ring-action --direction=cw --mode=2 keybinding "x"

$ gsetwacom tablet "056A:0357" map-to-monitor --connector DP-1
```
And for stylus configuration:
```
$ gsetwacom stylus 99800b93 show
pressure-curve=[0, 38, 62, 100]
eraser-pressure-curve=[0, 0, 100, 100]
button-action='default'
secondary-button-action='default'
tertiary-button-action='default'

$ gsetwacom stylus 99800b93 set-button-action secondary back


# Huion styli don't have a serial number so we just specify the tablet vid/pid
$ gsetwacom stylus "0256C:0066" set-button-action primary middle
```

## Notes

### No configuration verification

Right now `gsetwacom` is a simple wrapper around dconf/gsettings. It does not verify whether
configuration makes sense for your specific device. For example you will be able to
configure the third ring or button Z on a device with no rings or buttons. The configuration
will be *written* but it will never be *read* by mutter.

This is an inherent limitation of relocatable GSettings. To add this type of error checking
`gsetwacom` would need to fetch information from other sources, e.g. libwacom. This is not
currently implemented.

### No serial number detection

`gsetwacom` cannot detect a stylus serial number, external tools need to be used to
find the serial number of a stylus. The `gsetwacom list-styli` tool currently uses
the gnome-control-center (GNOME Settings) cache file for styli - this only works
where GNOME Settings has "seen" the stylus before by bringing it into proximity
above the GNOME Settings window.

## License

`gsetwacom` is distributed under the terms of the [MIT](https://spdx.org/licenses/MIT.html) license.
