# SPDX-FileCopyrightText: 2024-present Red Hat, Inc
#
# SPDX-License-Identifier: MIT

from dataclasses import dataclass
from pathlib import Path
from lxml import etree
from gi.repository import Gio, GLib  # type: ignore
import os
import logging
import string

import click
import rich.logging

logger = logging.getLogger("uji")
logger.addHandler(rich.logging.RichHandler())
logger.setLevel(logging.ERROR)


@dataclass
class Settings:
    path: str
    settings: Gio.Settings | None


@click.group()
@click.option("-v", "--verbose", count=True, help="increase verbosity")
@click.option("--quiet", "verbose", flag_value=0)
@click.pass_context
def gsetwacom(ctx, verbose: int):
    verbose_levels = {
        0: logging.ERROR,
        1: logging.INFO,
        2: logging.DEBUG,
    }
    logger.setLevel(verbose_levels.get(verbose, 0))


@gsetwacom.command()
def list_devices():
    """
    List all potential devices found on this system.

    This uses udev, a device listed here may not be available in the
    compositor and/or currently have configuration set.
    """
    import pyudev

    context = pyudev.Context()
    for device in filter(
        lambda d: Path(d.sys_path).name.startswith("event"),
        context.list_devices(subsystem="input"),
    ):
        if device.get("ID_INPUT_TABLET", "0") != "1":
            continue

        vid = int(device.get("ID_VENDOR_ID", "0"), 16)
        pid = int(device.get("ID_MODEL_ID", "0"), 16)
        name = device.get("NAME")
        if name is None:
            name = next(device.ancestors).get("NAME")

        # udev NAME is already in quotes
        print(f"- {name} ({vid:04X}:{pid:04X})")


@gsetwacom.group()
@click.argument("device", type=str)
@click.pass_context
def tablet(ctx, device):
    """
    Show or change configuration for a tablet device.

    DEVICE is a vendor/product ID tuple in the form 1234:abcd.
    """
    vid, pid = [int(x, 16) for x in device.split(":")]
    path = f"/org/gnome/desktop/peripherals/tablets/{vid:04x}:{pid:04x}/"
    schema = "org.gnome.desktop.peripherals.tablet"
    ctx.obj = Settings(path, Gio.Settings.new_with_path(schema, path))


@tablet.command(name="show")
@click.pass_context
def tablet_show(ctx):
    """
    Show the current configuraton of the given tablet DEVICE.
    """
    settings = ctx.obj.settings
    keys = ("area", "keep-aspect", "left-handed", "mapping", "output")
    for key in keys:
        print(f"{key}={settings.get_value(key)}")


@tablet.command(name="set-left-handed")
@click.argument("left-handed", type=bool)
@click.pass_context
def tablet_set_left_handed(ctx, left_handed: bool):
    """
    Change the left-handed configuration of this device
    """
    settings = ctx.obj.settings
    settings.set_boolean("left-handed", left_handed)


@tablet.command(name="set-absolute")
@click.argument("absolute", type=bool)
@click.pass_context
def tablet_set_absolute(ctx, absolute: bool):
    """
    Change the left-handed configuration of this device
    """
    settings = ctx.obj.settings
    settings.set_boolean("absolute", "absolute" if absolute else "relative")


@tablet.command(name="set-area")
@click.argument("x1", type=float)
@click.argument("y1", type=float)
@click.argument("x2", type=float)
@click.argument("y2", type=float)
@click.pass_context
def tablet_set_area(ctx, x1: float, y1: float, x2: float, y2: float):
    """
    Change the area the tablet is mapped to. All input parameters are percentages.
    """
    settings = ctx.obj.settings
    settings.set_value("area", GLib.Variant("ad", [x1, y1, x2, y2]))


@tablet.command(name="map-to-monitor")
@click.option("--vendor", type=str, default=None)
@click.option("--product", type=str, default=None)
@click.option("--serial", type=str, default=None)
@click.option("--connector", type=str, default=None)
@click.pass_context
def tablet_map_to_monitor(
    ctx,
    vendor: str | None,
    product: str | None,
    serial: str | None,
    connector: str | None,
):
    """
    Map the tablet to a given monitor. The monitor may be specified with one or more
    of the vendor, product, serial or connector.

    Note: this only works if the $XDG_CONFIG_HOME/monitors.xml file only
    has one matching configuration per screen for the given set of specifiers.
    """
    xdg = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    monitors = etree.parse(xdg / "monitors.xml")
    args = {
        "connector": connector,
        "vendor": vendor,
        "product": product,
        "serial": serial,
    }
    if all(args[key] is None for key in args):
        raise click.UsageError(
            "One of --vendor, --product, --serial or --connector has to be provided"
        )

    for monitor in monitors.iterfind(".//monitorspec"):
        data = {
            "connector": monitor.find("connector").text,
            "vendor": monitor.find("vendor").text,
            "product": monitor.find("product").text,
            "serial": monitor.find("serial").text,
        }
        if any(args[key] is not None and args[key] != data[key] for key in args):
            continue

        settings = ctx.obj.settings
        settings.set_value(
            "output",
            GLib.Variant(
                "as",
                [data["vendor"], data["product"], data["serial"], data["connector"]],
            ),
        )
        break


def change_action(path: str, action: str, keybinding: str | None):
    settings = Gio.Settings.new_with_path(
        "org.gnome.desktop.peripherals.tablet.pad-button", path
    )

    if action == "keybinding":
        if keybinding is None:
            raise click.UsageError("Keybinding must be provided for action keybinding")
    else:
        if keybinding is not None:
            raise click.UsageError("Keybinding is only valid for action keybinding")

    val = {
        "none": 0,
        "help": 1,
        "switch-monitor": 2,
        "keybinding": 3,
    }[action]

    if keybinding is not None:
        settings.set_string("keybinding", keybinding)
    settings.set_enum("action", val)


@tablet.command(name="set-ring-action")
@click.option("--ring", type=int, default=1, help="The ring number to change")
@click.option("--mode", type=int, default=0, help="The zero-indexed mode")
@click.option(
    "--direction",
    type=click.Choice(["cw", "ccw"]),
    default="cw",
    help="The ring movement direction",
)
@click.argument(
    "action", type=click.Choice(["none", "help", "switch-monitor", "keybinding"])
)
@click.argument(
    "keybinding",
    type=str,
    required=False,
)
@click.pass_context
def tablet_set_ring_action(
    ctx, ring: int, mode: int, direction: str, action: str, keybinding: str | None
):
    """
    Change the action the tablet ring is mapped to for a movement direction and in a given mode.
    """
    r = chr(ord("A") + ring - 1)  # ring 1 -> ringA
    subpath = f"ring{r}-{direction}-mode-{mode}"
    path = f"{ctx.obj.path}{subpath}/"
    change_action(path, action, keybinding)


@tablet.command(name="set-strip-action")
@click.option("--strip", type=int, default=1, help="The strip number to change")
@click.option("--mode", type=int, default=0, help="The zero-indexed mode")
@click.option(
    "--direction",
    type=click.Choice(["up", "down"]),
    default="cw",
    help="The strip movement direction",
)
@click.argument(
    "action", type=click.Choice(["none", "help", "switch-monitor", "keybinding"])
)
@click.argument(
    "keybinding",
    type=str,
    required=False,
)
@click.pass_context
def tablet_set_strip_action(
    ctx, strip: int, mode: int, direction: str, action: str, keybinding: str | None
):
    """
    Change the action the tablet strip is mapped to for a movement direction and in a given mode.
    """
    r = chr(ord("A") + strip - 1)  # strip 1 -> stripA
    subpath = f"strip{r}-{direction}-mode-{mode}"
    path = f"{ctx.obj.path}{subpath}/"
    change_action(path, action, keybinding)


@tablet.command(name="set-button-action")
@click.argument("button", type=click.Choice(string.ascii_uppercase))
@click.argument(
    "action", type=click.Choice(["none", "help", "switch-monitor", "keybinding"])
)
@click.argument(
    "keybinding",
    type=str,
    required=False,
)
@click.pass_context
def tablet_set_button_action(ctx, button: str, action: str, keybinding: str | None):
    """
    Change the action the tablet button is mapped to.
    """
    subpath = f"button{button}"
    path = f"{ctx.obj.path}{subpath}/"
    change_action(path, action, keybinding)


@gsetwacom.group()
@click.argument("stylus", type=str)
@click.pass_context
def stylus(ctx, stylus):
    """
    Show or change configuration for a stylus tool.

    STYLUS is a hexadecimal tool serial or for tools that do not support unique
    tool serials it is the vendor/product ID tuple of the tablet in the form 1234:abcd.
    """
    if ":" in stylus:
        vid, pid = [int(x, 16) for x in stylus.split(":")]
        serial = f"default-{vid:04x}:{pid:04x}"
    else:
        serial = int(stylus, 16)
        serial = f"{serial:x}"

    path = f"/org/gnome/desktop/peripherals/stylus/{serial}/"
    schema = "org.gnome.desktop.peripherals.tablet.stylus"
    ctx.obj = Settings(path, Gio.Settings.new_with_path(schema, path))


@stylus.command(name="show")
@click.pass_context
def stylus_show(ctx):
    """
    Show the current configuraton of the given STYLUS.
    """
    settings = ctx.obj.settings
    keys = (
        "pressure-curve",
        "eraser-pressure-curve",
        "button-action",
        "secondary-button-action",
        "tertiary-button-action",
    )
    for key in keys:
        print(f"{key}={settings.get_value(key)}")


@stylus.command(name="set-pressure-curve")
@click.option("--eraser", is_flag=True, help="Change the eraser pressure curve")
@click.argument("x1", type=float)
@click.argument("y1", type=float)
@click.argument("x2", type=float)
@click.argument("y2", type=float)
@click.pass_context
def stylus_set_left_handed(ctx, eraser: bool, x1: int, y1: int, x2: int, y2: int):
    """
    Change the pressure configuration of this stylus or eraser.

    The given arguments must be in the range [0, 100] and describe the two points BC
    of a bezier curve ABCD where A = (0, 0) and D = (100, 100).
    """
    settings = ctx.obj.settings
    key = "eraser-pressure-curve" if eraser else "pressure-curve"
    settings.set_value(key, GLib.Variant("ai", [x1, y1, x2, y2]))


@stylus.command(name="set-button-action")
@click.argument("button", type=click.Choice(["primary", "secondary", "tertiary"]))
@click.argument(
    "action", type=click.Choice(["left", "middle", "right", "back", "forward"])
)
@click.pass_context
def stylus_set_button_action(ctx, button: str, action: str):
    """
    Change the button action of this stylus or eraser.
    """
    settings = ctx.obj.settings
    key = "button-action"
    if button != "primary":
        key = f"{button}-{key}"

    #
    val = {
        "left": 0,
        "middle": 1,
        "right": 2,
        "back": 3,
        "forward": 4,
    }[action]
    settings.set_enum(key, val)


def main():
    gsetwacom()


if __name__ == "__main__":
    main()
