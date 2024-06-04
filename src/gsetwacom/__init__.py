# SPDX-FileCopyrightText: 2024-present Red Hat, Inc
#
# SPDX-License-Identifier: MIT

from dataclasses import dataclass
from pathlib import Path
from lxml import etree
from gi.repository import Gio, GLib  # type: ignore
import os
import logging

import click
import rich.logging

logger = logging.getLogger("uji")
logger.addHandler(rich.logging.RichHandler())
logger.setLevel(logging.ERROR)


@dataclass
class Settings:
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
    ctx.obj = Settings(Gio.Settings.new_with_path(schema, path))


@tablet.command(name="show")
@click.pass_context
def tablet_show(ctx):
    """
    Show the current configuraton of the given tablet DEVICE.
    """
    settings = ctx.obj.settings
    keys = ("area", "keep-aspect", "mapping", "output")
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


def main():
    gsetwacom()


if __name__ == "__main__":
    main()
