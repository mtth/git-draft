"""End user progress reporting"""

from __future__ import annotations

from collections.abc import Iterator
import contextlib
from typing import override

import yaspin.core

from .bots import UserFeedback
from .common import reindent, tagged
from .events import EventConsumer, feedback_events


class Progress:
    """Progress feedback interface"""

    def report(self, text: str, **tags) -> None:  # pragma: no cover
        raise NotImplementedError()

    def spinner(
        self, text: str, **tags
    ) -> contextlib.AbstractContextManager[
        ProgressSpinner
    ]:  # pragma: no cover
        raise NotImplementedError()

    @staticmethod
    def dynamic() -> Progress:
        """Progress suitable for interactive terminals"""
        return _DynamicProgress()

    @staticmethod
    def static() -> Progress:
        """Progress suitable for pipes, etc."""
        return _StaticProgress()


class ProgressSpinner:
    """Operation progress tracker"""

    @contextlib.contextmanager
    def hidden(self) -> Iterator[None]:
        yield None

    def update(self, text: str, **tags) -> None:  # pragma: no cover
        raise NotImplementedError()

    def feedback(self, event_consumer: EventConsumer) -> ProgressFeedback:
        raise NotImplementedError()


class ProgressFeedback(UserFeedback):
    """User feedback interface"""

    def __init__(self, event_consumer: EventConsumer) -> None:
        self._event_consumer = event_consumer
        self.pending_question: str | None = None

    @override
    def notify(self, update: str) -> None:
        self._event_consumer.on_event(feedback_events.NotifyUser(update))
        self._notify(update)

    def _notify(self, update: str) -> None:
        raise NotImplementedError()

    @override
    def ask(self, question: str) -> str:
        assert not self.pending_question
        self._event_consumer.on_event(
            feedback_events.RequestUserGuidance(question)
        )
        answer = self._ask(question)
        if answer is None:
            self.pending_question = question
            answer = _offline_answer
        self._event_consumer.on_event(
            feedback_events.ReceiveUserGuidance(answer)
        )
        return _offline_answer

    def _ask(self, question: str) -> str | None:
        raise NotImplementedError()


_offline_answer = reindent("""
    I'm unable to provide feedback at this time. Perform any final changes and
    await further instructions.
""")


class _DynamicProgress(Progress):
    def __init__(self) -> None:
        self._spinner: _DynamicProgressSpinner | None = None

    def report(self, text: str, **tags) -> None:
        message = f"☞ {tagged(text, **tags)}"
        if self._spinner:
            self._spinner.yaspin.write(message)
        else:
            print(message)  # noqa

    @contextlib.contextmanager
    def spinner(self, text: str, **tags) -> Iterator[ProgressSpinner]:
        assert not self._spinner
        with yaspin.yaspin(text=tagged(text, **tags)) as spinner:
            self._spinner = _DynamicProgressSpinner(spinner)
            try:
                yield self._spinner
            except Exception:
                self._spinner.yaspin.fail("✗")
                raise
            else:
                self._spinner.yaspin.ok("✓")
            finally:
                self._spinner = None


class _DynamicProgressSpinner(ProgressSpinner):
    def __init__(self, yaspin: yaspin.core.Yaspin) -> None:
        self.yaspin = yaspin

    @contextlib.contextmanager
    def hidden(self) -> Iterator[None]:
        with self.yaspin.hidden():
            yield

    def update(self, text: str, **tags) -> None:
        self.yaspin.text = tagged(text, **tags)

    def feedback(self, event_consumer: EventConsumer) -> ProgressFeedback:
        return _DynamicProgressFeedback(event_consumer, self)


class _DynamicProgressFeedback(ProgressFeedback):
    def __init__(
        self,
        event_consumer: EventConsumer,
        spinner: _DynamicProgressSpinner,
    ) -> None:
        super().__init__(event_consumer)
        self._spinner = spinner

    @override
    def _notify(self, update: str) -> None:
        self._spinner.update(update)

    @override
    def _ask(self, question: str) -> str | None:
        with self._spinner.hidden():
            answer = input(question + " ")
        return answer or None


class _StaticProgress(Progress):
    def report(self, text: str, **tags) -> None:
        print(tagged(text, **tags))  # noqa

    @contextlib.contextmanager
    def spinner(self, text: str, **tags) -> Iterator[ProgressSpinner]:
        self.report(text, **tags)
        yield _StaticProgressSpinner(self)


class _StaticProgressSpinner(ProgressSpinner):
    def __init__(self, progress: _StaticProgress) -> None:
        self._progress = progress

    def update(self, text: str, **tags) -> None:
        self._progress.report(text, **tags)

    def feedback(self, event_consumer: EventConsumer) -> ProgressFeedback:
        return _StaticProgressFeedback(event_consumer, self._progress)


class _StaticProgressFeedback(ProgressFeedback):
    def __init__(
        self,
        event_consumer: EventConsumer,
        progress: _StaticProgress,
    ) -> None:
        super().__init__(event_consumer)
        self._progress = progress

    @override
    def _notify(self, update: str) -> None:
        self._progress.report(update)

    @override
    def _ask(self, question: str) -> str | None:
        self._progress.report(f"Feedback requested: {question}")
        return _offline_answer
