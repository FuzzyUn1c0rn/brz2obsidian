# Keep diagnostic delivery independent of operation authority

Build user-visible diagnostics from admitted codes, static guidance, and
allowed artifact paths. Raw provider messages, reference lists, candidate lists,
and stderr can carry authored content. Drain worker stderr to let the child
finish, retain only a bounded transient buffer, and discard it at the boundary.
A detailed diagnostic reason needs its original code so a valid reason cannot
be transplanted to an unrelated failure.

Keep the worker control reader available when stdout blocks. Progress
observations can wait or be discarded, while terminal and control responses
take priority. Run presentation callbacks outside transport locks and let the
transport allocate wire sequence numbers. A broken output channel leaves the
parent without confirmed publication authority even when a native operation
has produced a result. Continue draining the channel and require a fresh
qualified observation before proceeding.

On Windows, yield blocked worker input without retaining a native I/O lock
because extension initialization can otherwise deadlock. After a sealed close
reply, let the parent release stdin and join before interpreter shutdown so
no thread still owns buffered standard I/O.
