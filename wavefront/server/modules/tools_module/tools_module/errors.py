class ToolCallFailed(Exception):
    """A registry function could not do what it was called for.

    An agent gets the message back as the tool's result so the model can react
    (``ToolLoader.load_tool``). A function node has no model to read it, so
    there it propagates and fails the node instead of passing on as output.
    """
