# SPDX-FileCopyrightText: 2024-present Red Hat, Inc
#
# SPDX-License-Identifier: MIT

from __future__ import annotations

import asyncio
import logging
import os
import string
from dataclasses import asdict, dataclass
from functools import wraps
from pathlib import Path

import click
import dbus_fast
import dbus_fast.aio
import rich.logging
from gi.repository import Gio, GLib  # type: ignore

logger = logging.getLogger("uji")
logger.addHandler(rich.logging.RichHandler())
logger.setLevel(logging.ERROR)


@dataclass
class Settings:
    path: str
    settings: Gio.Settings

    def set_value(self, key, value):
        if self.has_key(key):
            self.settings.set_value(key, value)
        else:
            click.secho(f"WARNING: {key} does not exist in the schema, ignoring")

    def set_enum(self, key, value):
        if self.has_key(key):
            self.settings.set_enum(key, value)
        else:
            click.secho(f"WARNING: {key} does not exist in the schema, ignoring")

    def set_string(self, key, value):
        if self.has_key(key):
            self.settings.set_string(key, value)
        else:
            click.secho(f"WARNING: {key} does not exist in the schema, ignoring")

    def set_boolean(self, key, value):
        if self.has_key(key):
            self.settings.set_boolean(key, value)
        else:
            click.secho(f"WARNING: {key} does not exist in the schema, ignoring")

    def has_key(self, key) -> bool:
        return self.settings.props.settings_schema.has_key(key)

    def get_value(self, key):
        return self.settings.get_value(key)

    @classmethod
    def for_tablet(cls, vid: int, pid: int):
        path = f"/org/gnome/desktop/peripherals/tablets/{vid:04x}:{pid:04x}/"
        schema = "org.gnome.desktop.peripherals.tablet"
        return cls(path, Gio.Settings.new_with_path(schema, path))

    @classmethod
    def for_stylus_with_serial(cls, serial):
        path = f"/org/gnome/desktop/peripherals/stylus/{serial:x}/"
        schema = "org.gnome.desktop.peripherals.tablet.stylus"
        return cls(path, Gio.Settings.new_with_path(schema, path))

    @classmethod
    def for_stylus(cls, vid: int, pid: int):
        path = f"/org/gnome/desktop/peripherals/stylus/default-{vid:04x}:{pid:04x}/"
        schema = "org.gnome.desktop.peripherals.tablet.stylus"
        return cls(path, Gio.Settings.new_with_path(schema, path))


def print_tablet_settings(settings, indent=0):
    indent = " " * indent
    keys = ("area", "keep-aspect", "left-handed", "mapping", "output")
    click.echo(f"{indent}settings:")
    for key in filter(lambda k: settings.has_key(k), keys):
        click.echo(f"{indent}  {key}: {settings.get_value(key)}")


def print_stylus_settings(settings, indent=0):
    keys = (
        "pressure-curve",
        "eraser-pressure-curve",
        "pressure-range",
        "eraser-pressure-range",
        "button-action",
        "secondary-button-action",
        "tertiary-button-action",
        "button-keybinding",
        "secondary-button-keybinding",
        "tertiary-button-keybinding",
    )
    indent = " " * indent
    click.echo(f"{indent}settings:")
    for key in filter(lambda k: settings.has_key(k), keys):
        click.echo(f"{indent}  {key}: {settings.get_value(key)}")


@click.group()
@click.option("-v", "--verbose", count=True, help="increase verbosity")
@click.option("--quiet", "verbose", flag_value=0)
def gsetwacom(verbose: int):
    verbose_levels = {
        0: logging.ERROR,
        1: logging.INFO,
        2: logging.DEBUG,
    }
    logger.setLevel(verbose_levels.get(verbose, 0))


@gsetwacom.command()
def list_tablets():
    """
    List all potential devices found on this system.

    This uses udev, a device listed here may not be available in the
    compositor and/or currently have configuration set.
    """
    import pyudev

    @dataclass
    class Tablet:
        name: str
        vid: int
        pid: int

    tablets = []
    context = pyudev.Context()
    for device in filter(
        lambda d: Path(d.sys_path).name.startswith("event"),
        context.list_devices(subsystem="input"),
    ):
        if (
            device.get("ID_INPUT_TABLET", "0") != "1"
            or device.get("ID_INPUT_TABLET_PAD", "0") == "1"
            or device.get("ID_INPUT_TOUCHPAD", "0") == "1"
        ):
            continue

        vid = int(device.get("ID_VENDOR_ID", "0"), 16)
        pid = int(device.get("ID_MODEL_ID", "0"), 16)
        name = device.get("NAME")
        if name is None:
            name = next(device.ancestors).get("NAME")
        name = name.lstrip('"').rstrip('"')
        tablets.append(Tablet(name, vid, pid))

    if not tablets:
        click.secho("No devices found")
        return

    click.echo("devices:")
    for tablet in tablets:
        click.echo(f'- name: "{tablet.name}"')
        click.echo(f'  usbid: "{tablet.vid:04X}:{tablet.pid:04X}"')


@gsetwacom.command()
def list_styli():
    """
    List the styli previously seen on this system.

    Only styli with unique serial numbers are listed.

    This currently uses the gnome-control-center cache file, a device may not
    be available until it has been brought into proximity above the
    control center.
    """
    from configparser import ConfigParser

    xdg = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    config = ConfigParser()
    config.read(xdg / "gnome-control-center" / "wacom" / "tools")
    if not config.sections():
        click.secho("No styli found")
        return

    click.echo("styli:")
    for section in config.sections():
        click.echo(f" - serial number: {section}")


@gsetwacom.group()
@click.argument("device", type=str)
@click.pass_context
def tablet(ctx, device):
    """
    Show or change configuration for a tablet device.

    DEVICE is a vendor/product ID tuple in the form 1234:abcd.
    """
    vid, pid = (int(x, 16) for x in device.split(":"))
    ctx.obj = Settings.for_tablet(vid, pid)


@tablet.command(name="show")
@click.pass_context
def tablet_show(ctx):
    """
    Show the current configuraton of the given tablet DEVICE.
    """
    print_tablet_settings(ctx.obj)


@tablet.command(name="set-left-handed")
@click.argument("left-handed", type=bool)
@click.pass_context
def tablet_set_left_handed(ctx, left_handed: bool):
    """
    Change the left-handed configuration of this device
    """
    settings = ctx.obj
    settings.set_boolean("left-handed", left_handed)


@tablet.command(name="set-keep-aspect")
@click.argument("keep-aspect-ratio", type=bool)
@click.pass_context
def tablet_set_keep_aspect(ctx, keep_aspect_ratio: bool):
    """
    Change the keep-aspect configuration of this device

    A device with keep-aspect enabled will reduce its available area
    to match the aspect ratio of the monitor it is mapped to.
    """
    settings = ctx.obj
    settings.set_boolean("keep-aspect", keep_aspect_ratio)


@tablet.command(name="set-absolute")
@click.argument("absolute", type=bool)
@click.pass_context
def tablet_set_absolute(ctx, absolute: bool):
    """
    Change the left-handed configuration of this device
    """
    settings = ctx.obj
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
    settings = ctx.obj
    settings.set_value("area", GLib.Variant("ad", [x1, y1, x2, y2]))


def coro(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        return asyncio.run(f(*args, **kwargs))

    return wrapper


@tablet.command(name="map-to-monitor")
@coro
@click.option("--vendor", type=str, default=None)
@click.option("--product", type=str, default=None)
@click.option("--serial", type=str, default=None)
@click.option("--connector", type=str, default=None)
@click.pass_context
async def tablet_map_to_monitor(
    ctx,
    vendor: str | None,
    product: str | None,
    serial: str | None,
    connector: str | None,
):
    """
    Map the tablet to a given monitor. The monitor may be specified with one or more
    of the vendor, product, serial or connector.
    """
    args = {
        "connector": connector,
        "vendor": vendor,
        "product": product,
        "serial": serial,
    }
    if all(args[key] is None for key in args):
        msg = "One of --vendor, --product, --serial or --connector has to be provided"
        raise click.UsageError(msg)

    bus = await dbus_fast.aio.MessageBus().connect()
    busname = "org.gnome.Mutter.DisplayConfig"
    objpath = "/org/gnome/Mutter/DisplayConfig"
    intf = "org.gnome.Mutter.DisplayConfig"
    introspection = await bus.introspect(busname, objpath)

    proxy_object = bus.get_proxy_object(busname, objpath, introspection)
    interface = proxy_object.get_interface(intf)

    state = await interface.call_get_current_state()
    _, monitors, _, _ = state  # serial, monitors, logical_monitors, properties

    @dataclass
    class Monitor:
        connector: str
        vendor: str
        product: str
        serial: str

    monitors = (Monitor(*mdata) for (mdata, *_) in monitors)

    for monitor in monitors:
        logger.info("Monitor on %s vendor '%s' product '%s' serial '%s'", *asdict(monitor).values())
        if any(args[key] is not None and args[key] != getattr(monitor, key) for key in args):
            continue
        settings = ctx.obj
        settings.set_value(
            "output",
            GLib.Variant(
                "as",
                [monitor.vendor, monitor.product, monitor.serial, monitor.connector],
            ),
        )
        break
    else:
        msg = "Unable to find this monitor in the current configuration"
        raise click.UsageError(msg)


def change_action(path: str, action: str, keybinding: str | None):
    settings = Gio.Settings.new_with_path("org.gnome.desktop.peripherals.tablet.pad-button", path)

    if action == "keybinding":
        if keybinding is None:
            msg = "Keybinding must be provided for action keybinding"
            raise click.UsageError(msg)
    else:  # noqa: PLR5501
        if keybinding is not None:
            msg = "Keybinding is only valid for action keybinding"
            raise click.UsageError(msg)

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
@click.argument("action", type=click.Choice(["none", "help", "switch-monitor", "keybinding"]))
@click.argument(
    "keybinding",
    type=str,
    required=False,
)
@click.pass_context
def tablet_set_ring_action(ctx, ring: int, mode: int, direction: str, action: str, keybinding: str | None):
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
@click.argument("action", type=click.Choice(["none", "help", "switch-monitor", "keybinding"]))
@click.argument(
    "keybinding",
    type=str,
    required=False,
)
@click.pass_context
def tablet_set_strip_action(ctx, strip: int, mode: int, direction: str, action: str, keybinding: str | None):
    """
    Change the action the tablet strip is mapped to for a movement direction and in a given mode.
    """
    r = chr(ord("A") + strip - 1)  # strip 1 -> stripA
    subpath = f"strip{r}-{direction}-mode-{mode}"
    path = f"{ctx.obj.path}{subpath}/"
    change_action(path, action, keybinding)


@tablet.command(name="set-button-action")
@click.argument("button", type=click.Choice(string.ascii_uppercase))
@click.argument("action", type=click.Choice(["none", "help", "switch-monitor", "keybinding"]))
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
        vid, pid = (int(x, 16) for x in stylus.split(":"))
        settings = Settings.for_stylus(vid, pid)
    else:
        serial = int(stylus, 16)
        settings = Settings.for_stylus_with_serial(serial)

    ctx.obj = settings


@stylus.command(name="show")
@click.pass_context
def stylus_show(ctx):
    """
    Show the current configuraton of the given STYLUS.
    """
    print_stylus_settings(ctx.obj)


@stylus.command(name="set-pressure-curve")
@click.option("--eraser", is_flag=True, help="Change the eraser pressure curve")
@click.argument("x1", type=float)
@click.argument("y1", type=float)
@click.argument("x2", type=float)
@click.argument("y2", type=float)
@click.pass_context
def stylus_set_pressure_curve(ctx, eraser: bool, x1: int, y1: int, x2: int, y2: int):
    """
    Change the pressure configuration of this stylus or eraser.

    The given arguments must be in the range [0, 100] and describe the two points BC
    of a bezier curve ABCD where A = (0, 0) and D = (100, 100).
    """
    settings = ctx.obj
    key = "eraser-pressure-curve" if eraser else "pressure-curve"
    settings.set_value(key, GLib.Variant("ai", [x1, y1, x2, y2]))


@stylus.command(name="set-pressure-range")
@click.option("--eraser", is_flag=True, help="Change the eraser pressure range")
@click.argument("minimum", type=int)
@click.argument("maximum", type=int)
@click.pass_context
def stylus_set_pressure_range(ctx, eraser: bool, minimum: int, maximum: int):
    """
    Change the pressure range of this stylus or eraser.

    The given arguments must be in the range [0, 100].
    """
    settings = ctx.obj
    key = "eraser-pressure-range" if eraser else "pressure-range"
    settings.set_value(key, GLib.Variant("ai", [minimum, maximum]))


@stylus.command(name="set-button-action")
@click.argument("button", type=click.Choice(["primary", "secondary", "tertiary"]))
@click.argument(
    "action", type=click.Choice(["left", "middle", "right", "back", "forward", "switch-monitor", "keybinding"])
)
@click.argument(
    "keybinding",
    type=str,
    required=False,
)
@click.pass_context
def stylus_set_button_action(ctx, button: str, action: str, keybinding: str | None):
    """
    Change the button action of this stylus or eraser.
    """
    if action == "keybinding":
        if keybinding is None:
            msg = "Keybinding must be provided for action keybinding"
            raise click.UsageError(msg)
    else:  # noqa: PLR5501
        if keybinding is not None:
            msg = "Keybinding is only valid for action keybinding"
            raise click.UsageError(msg)

    settings = ctx.obj

    button_prefix = {
        "primary": "button",
        "secondary": "secondary-button",
        "tertiary": "tertiary-button",
    }[button]

    if keybinding is not None:
        key = f"{button_prefix}-keybinding"
        settings.set_string(key, keybinding)

    key = f"{button_prefix}-action"
    val = {"left": 0, "middle": 1, "right": 2, "back": 3, "forward": 4, "switch-monitor": 5, "keybinding": 6}[action]
    settings.set_enum(key, val)


def main():
    gsetwacom()


if __name__ == "__main__":
    main()
