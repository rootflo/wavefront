from typing import Any, Union, Callable, Optional, Dict
from dataclasses import dataclass, field
from flo_ai.common.flo_logger import get_logger


@dataclass
class FloCallbackResponse:
    type: str
    name: Optional[str] = None
    model_name: Optional[str] = None
    input: Optional[str] = None
    output: Optional[str] = None
    error: Union[Exception, KeyboardInterrupt, None] = None
    args: Dict = field(default_factory=dict)


class FloToolCallback:
    def __init__(self) -> None:
        pass

    def on_tool_start(
        self, name: str, input: Any, **kwargs: Any
    ) -> Optional[FloCallbackResponse]:
        pass

    def on_tool_end(
        self, name: str, output: Any, **kwargs: Any
    ) -> Optional[FloCallbackResponse]:
        pass

    def on_tool_error(
        self, name: str, error: Union[Exception, KeyboardInterrupt], **kwargs: Any
    ) -> Optional[FloCallbackResponse]:
        pass


class FloAgentCallback:
    def __init__(self) -> None:
        pass

    def on_agent_start(
        self, name: str, model_name: str, input: Any, **kwargs: Any
    ) -> Optional[FloCallbackResponse]:
        pass

    def on_agent_end(
        self, name: str, model_name: str, output: Any, **kwargs: Any
    ) -> Optional[FloCallbackResponse]:
        pass

    def on_agent_error(
        self,
        name: str,
        model_name: str,
        error: Union[Exception, KeyboardInterrupt],
        **kwargs: Any,
    ) -> Optional[FloCallbackResponse]:
        pass


class FloRouterCallback:
    def __init__(self) -> None:
        pass

    def on_router_start(
        self, name: str, model_name: str, input: Any, **kwargs: Any
    ) -> Optional[FloCallbackResponse]:
        pass

    def on_router_end(
        self, name: str, model_name: str, output: Any, **kwargs: Any
    ) -> Optional[FloCallbackResponse]:
        pass

    def on_router_error(
        self,
        name: str,
        model_name: str,
        error: Union[Exception, KeyboardInterrupt],
        **kwargs: Any,
    ) -> None:
        Optional[FloCallbackResponse]


def safe_call_cb(func, cb_response: FloCallbackResponse, ignore_error=True):
    try:
        func(cb_response)
    except Exception as e:
        if ignore_error:
            get_logger().warning(e)
        else:
            raise e


class FunctionalFloToolCallbackImpl(FloToolCallback):
    def __init__(self, func: Callable, ignore_error: bool = True) -> None:
        super().__init__()
        self.func = func
        self.ignore_error = ignore_error

    def on_tool_start(
        self, name: str, input: Any, **kwargs: Any
    ) -> Optional[FloCallbackResponse]:
        cb_response = FloRouterCallback('on_tool_start', name, input=input, args=kwargs)
        safe_call_cb(self.func, cb_response, self.ignore_error)
        return cb_response

    def on_tool_end(
        self, name: str, output: Any, **kwargs: Any
    ) -> Optional[FloCallbackResponse]:
        cb_response = FloRouterCallback('on_tool_end', name, output=output, args=kwargs)
        safe_call_cb(self.func, cb_response, self.ignore_error)
        return cb_response

    def on_tool_error(
        self, name: str, error: Union[Exception, KeyboardInterrupt], **kwargs: Any
    ) -> Optional[FloCallbackResponse]:
        cb_response = FloRouterCallback('on_tool_error', name, error=error, args=kwargs)
        safe_call_cb(self.func, cb_response, self.ignore_error)
        return cb_response


class FunctionalFloAgentCallbackImpl(FloAgentCallback):
    def __init__(self, func: Callable, ignore_error: bool = True) -> None:
        super().__init__()
        self.func = func
        self.ignore_error = ignore_error

    def on_agent_start(
        self, name: str, model_name: str, input: Any, **kwargs: Any
    ) -> Any:
        cb_response = FloCallbackResponse(
            'on_agent_start', name, input=input, args=kwargs, model_name=model_name
        )
        safe_call_cb(self.func, cb_response, self.ignore_error)
        return cb_response

    def on_agent_end(
        self, name: str, model_name: str, output: Any, **kwargs: Any
    ) -> None:
        cb_response = FloCallbackResponse(
            'on_agent_end', name, output=output, args=kwargs, model_name=model_name
        )
        safe_call_cb(self.func, cb_response, self.ignore_error)
        return cb_response

    def on_agent_error(
        self,
        name: str,
        model_name: str,
        error: Union[Exception, KeyboardInterrupt],
        **kwargs: Any,
    ) -> None:
        cb_response = FloCallbackResponse(
            'on_agent_error', name, error=error, args=kwargs, model_name=model_name
        )
        safe_call_cb(self.func, cb_response, self.ignore_error)
        return cb_response


class FunctionalFloRouterCallbackImpl(FloRouterCallback):
    def __init__(self, func: Callable, ignore_error: bool = True) -> None:
        super().__init__()
        self.func = func
        self.ignore_error = ignore_error

    def on_router_start(
        self, name: str, model_name: str, input: Any, **kwargs: Any
    ) -> Any:
        cb_response = FloCallbackResponse(
            'on_router_start', name, input=input, args=kwargs, model_name=model_name
        )
        safe_call_cb(self.func, cb_response, self.ignore_error)
        return cb_response

    def on_router_end(
        self, name: str, model_name: str, output: Any, **kwargs: Any
    ) -> None:
        cb_response = FloCallbackResponse(
            'on_router_end', name, output=output, args=kwargs, model_name=model_name
        )
        safe_call_cb(self.func, cb_response, self.ignore_error)
        return cb_response

    def on_router_error(
        self,
        name: str,
        model_name: str,
        error: Union[Exception, KeyboardInterrupt],
        **kwargs: Any,
    ) -> None:
        cb_response = FloCallbackResponse(
            'on_router_error', name, error=error, args=kwargs, model_name=model_name
        )
        safe_call_cb(self.func, cb_response, self.ignore_error)
        return cb_response


class FloCallback(
    FunctionalFloToolCallbackImpl,
    FunctionalFloAgentCallbackImpl,
    FunctionalFloRouterCallbackImpl,
):
    def __init__(self, func: Callable, ignore_error: bool = True) -> None:
        FunctionalFloToolCallbackImpl.__init__(self, func, ignore_error)
        FunctionalFloAgentCallbackImpl.__init__(self, func, ignore_error)
        FunctionalFloRouterCallbackImpl.__init__(self, func, ignore_error)


def flo_tool_callback(func: Callable, ignore_error=True) -> FloToolCallback:
    return FunctionalFloToolCallbackImpl(func, ignore_error)


def flo_agent_callback(func: Callable, ignore_error=True) -> FloToolCallback:
    return FunctionalFloAgentCallbackImpl(func, ignore_error)


def flo_router_callback(func: Callable, ignore_error=True) -> FloRouterCallback:
    return FunctionalFloRouterCallbackImpl(func, ignore_error)


def flo_call_back(func: Callable, ignore_error=True) -> FloRouterCallback:
    return FloCallback(func, ignore_error)
