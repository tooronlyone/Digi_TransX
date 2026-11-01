# Frontend polling fixture review

The 21:23 whole-component run completed with 90 passing tests and one failure in
`polling does not repeatedly abort a slow initial conversation read`. Its first
read wait asserted zero requests instead of one. The unchanged production chat
code passed all 29 cases in the subsequent focused module run; that raw rerun is
recorded in `frontend-chat-regression-rerun.log`.

The test replaced every `window.setInterval`, including Testing Library's own
wait-loop interval. When React's first message effect had not run before the
first assertion, that wait could not check again. The mock also returned positive
IDs capable of colliding with jsdom's real timer IDs.

The fixture now captures only the application's 4,000 ms polling intervals,
forwards all other intervals to the original implementation, and assigns its
captured callbacks negative IDs. The assertions remain unchanged: exactly one
initial request, repeated simulated polls cause no extra requests or abort,
and the slow valid response is eventually displayed. No production chat code,
poll duration, or assertion was weakened.

The final whole-component outcome is recorded separately in
`frontend-final-vitest.log`.
