"""GTK interface of BigLinux Config."""


def set_label(widget, label: str) -> None:
    """Set GTK4 accessible label via Gtk.AccessibleProperty.LABEL."""
    from gi.repository import Gtk

    widget.update_property(
        [Gtk.AccessibleProperty.LABEL],
        [label],
    )
