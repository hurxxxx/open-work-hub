# Tests

Good:

- assert observable behavior through public interface
- use real code paths
- name capability, not internals
- survive refactor
- one logical behavior per test

Bad:

- mock internal collaborators
- test private methods
- assert call count/order unless public contract
- verify by bypassing the interface
- break on internal rename without behavior change
