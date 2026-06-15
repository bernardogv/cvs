class SubcommandPlugin:
    """Base class for CLI subcommand plugins."""

    PLUGIN_ORDERS = {
        "monitor": 999,
        "exec": 1000,  # High number to ensure exec appears last
    }

    def get_name(self):
        raise NotImplementedError

    def get_parser(self, subparsers):
        """Register subcommand with argparse subparsers."""
        raise NotImplementedError

    def get_epilog(self):
        """Return examples or help text for this subcommand. Default is empty."""
        return ""

    def get_order(self):
        """Return the display order for this plugin. Lower numbers appear first. Default is 0."""
        return self.PLUGIN_ORDERS.get(self.get_name(), 0)

    def run(self, args):
        """Run the subcommand logic."""
        raise NotImplementedError

    def describe(self):
        """Optional structured metadata for ``cvs describe`` (agent discovery).

        Override to expose semantics argparse cannot: a ``summary`` string, a
        ``read_only`` bool, an ``exit_codes`` dict, an ``input_files`` list
        (each ``{"arg", "format", "required_keys", "optional_keys"}``), and
        ``examples``. Default returns no extra metadata; ``cvs describe`` then
        falls back to argparse-derived args, help text, and the epilog.
        """
        return {}
