"""GTK interface of BigLinux Config."""

import os

FALLBACK_ICON = "application-x-executable"


def set_label(widget, label: str) -> None:
    """Set the accessible label read by screen readers."""
    from gi.repository import Gtk

    widget.update_property([Gtk.AccessibleProperty.LABEL], [label])


def app_image(icon: str, pixel_size: int):
    """Image for an application icon given as a theme name or a file path.

    Desktop-environment and some Flatpak icons do not exist in every icon
    theme; a missing name falls back to a generic application icon instead
    of GTK's "missing image" placeholder.
    """
    from gi.repository import Gdk, Gtk

    if icon.startswith("/"):
        image = (Gtk.Image.new_from_file(icon) if os.path.isfile(icon)
                 else Gtk.Image.new_from_icon_name(FALLBACK_ICON))
    else:
        display = Gdk.Display.get_default()
        theme = Gtk.IconTheme.get_for_display(display) if display else None
        name = icon if icon and (theme is None or theme.has_icon(icon)) else FALLBACK_ICON
        image = Gtk.Image.new_from_icon_name(name)
    image.set_pixel_size(pixel_size)
    return image
