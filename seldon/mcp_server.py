from mcp.server.fastmcp import FastMCP

mcp = FastMCP("seldon")


@mcp.tool()
def seldon_go(project_dir: str = ".", brief: bool = False) -> str:
    """Orient to a Seldon-managed project. Returns engineering standards,
    project context, latest handoff, current state, and available commands.

    Args:
        project_dir: Path to the project root (default: current directory).
            When left as ".", the SELDON_DEFAULT_PROJECT environment variable
            is used if set and contains a valid seldon.yaml.
        brief: If True, skip system CLAUDE.md for a shorter response
    """
    from seldon.commands.go import assemble_go_context
    return assemble_go_context(project_dir=project_dir, brief=brief)


def main():
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
