"""Implementation of coroutines without using ``async def``/``await`` keywords.

``@asyncio.coroutine`` and ``yield from`` are  used here instead.
"""
import asyncio
import errno
import signal

from pipenv.vendor.pexpect import EOF


@asyncio.coroutine
def expect_async(expecter, timeout=None):
    # First process data that was previously read - if it maches, we don't need
    # async stuff.
    idx = expecter.existing_data()
    if idx is not None:
        return idx
    if not expecter.spawn.async_pw_transport:
        pw = PatternWaiter()
        pw.set_expecter(expecter)
        transport, pw = yield from asyncio.get_event_loop().connect_read_pipe(
            lambda: pw, expecter.spawn
        )
        expecter.spawn.async_pw_transport = pw, transport
    else:
        pw, transport = expecter.spawn.async_pw_transport
        pw.set_expecter(expecter)
        transport.resume_reading()
    try:
        return (yield from asyncio.wait_for(pw.fut, timeout))
    except asyncio.TimeoutError as e:
        transport.pause_reading()
        return expecter.timeout(e)


@asyncio.coroutine
def repl_run_command_async(repl, cmdlines, timeout=-1):
    res = []
    repl.child.sendline(cmdlines[0])
    for line in cmdlines[1:]:
        yield from repl._expect_prompt(timeout=timeout, async_=True)
        res.append(repl.child.before)
        repl.child.sendline(line)

    # Command was fully submitted, now wait for the next prompt
    prompt_idx = yield from repl._expect_prompt(timeout=timeout, async_=True)
    if prompt_idx == 1:
        # We got the continuation prompt - command was incomplete
        repl.child.kill(signal.SIGINT)
        yield from repl._expect_prompt(timeout=1, async_=True)
        raise ValueError("Continuation prompt found - input was incomplete:")
    return "".join(res + [repl.child.before])


class PatternWaiter(asyncio.Protocol):
    transport = None

    def set_expecter(self, expecter):
        self.expecter = expecter
        self.fut = asyncio.Future()

    def found(self, result):
        pass

    def error(self, exc):
        if not self.fut.done():
            self.fut.set_exception(exc)
            self.transport.pause_reading()

    def connection_made(self, transport):
        pass

    def data_received(self, data):
        pass

    def eof_received(self):
        # N.B. If this gets called, async will close the pipe (the spawn object)
        # for us
        pass

    def connection_lost(self, exc):
        pass
