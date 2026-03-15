import click

from seldon.commands.init import init_command
from seldon.commands.status import status_command
from seldon.commands.rebuild import rebuild_command
from seldon.commands.artifact import artifact_group
from seldon.commands.link import link_group
from seldon.commands.result import result_group
from seldon.commands.task import task_group
from seldon.commands.session import briefing_command, closeout_command
from seldon.commands.paper import paper_group


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
main.add_command(result_group, name="result")
main.add_command(task_group, name="task")
main.add_command(briefing_command, name="briefing")
main.add_command(closeout_command, name="closeout")
main.add_command(paper_group, name="paper")
