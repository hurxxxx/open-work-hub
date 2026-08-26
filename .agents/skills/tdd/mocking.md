# Mocking

Mock only system boundaries:

- external APIs
- time/random
- filesystem when needed
- DB only when test DB is not the right seam

Do not mock owned modules/classes/functions. Prefer dependency injection and specific SDK-style boundary methods over a generic fetcher with conditional mocks.
