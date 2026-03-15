import click

from seldon.commands.init import init_command
from seldon.commands.status import status_command
from seldon.commands.rebuild import rebuild_command
from seldon.commands.artifact import artifact_group
from seldon.commands.link import link_group


@click.group()
@click.version_option()
def main():
    """Seldon — AI-assisted research artifact tracker."""
    pass


main.add_command(init_command, name="init")
main.add_command(status_command, name="status")
main.add_command(rebuild_command, name="rebuild")
main.add_command(artifact_group, name="artifact")
main.add_command(link_group, name="link")
