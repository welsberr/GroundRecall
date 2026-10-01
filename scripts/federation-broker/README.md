# Avida GroundRecall broker setup

These scripts provide a private SSH path to the nerdanel broker and a bounded
participant onboarding path for alatar and nerdanel. They do not publish or
promote memory records. Broker delivery still requires a separate receiver
subscription and local quarantine review.

The broker stays bound to nerdanel loopback port `18765`. The tunnel exposes it
only as alatar loopback port `18766`; do not bind the broker or tunnel to a LAN
or public interface. The existing GenieHive Batch tunnel on port `18765` is
left untouched.

Before use, publish or securely transfer a reviewed GroundRecall revision that
contains `groundrecall-broker` to alatar. The current nerdanel checkout may
contain uncommitted broker-client code; installing the public `main` branch
before that code is released may not work.

## Run order

1. On nerdanel, run `nerdanel-install-tunnel.sh`. It installs and starts a
   separate systemd user service. nerdanel must be able to SSH to alatar.
2. On nerdanel, run `nerdanel-provision-participant.sh avida-alatar` and
   `nerdanel-provision-participant.sh avida-nerdanel`. Each creates a separate
   non-admin token, updates the broker auth map, and recreates the broker.
3. Transfer only alatar's token with
   `nerdanel-transfer-alatar-token.sh /path/to/avida-alatar.token`.
   Nerdanel's participant token remains in the owner-only broker secrets
   directory; use that file directly when submitting its enrollment.
4. On alatar, install the released GroundRecall checkout with
   `alatar-install-client.sh /path/to/GroundRecall`. It tests the tunnel and
   token with the public broker capabilities endpoint.
5. Run `create-avida-enrollment.sh` separately on alatar and nerdanel. It
   creates host-specific keys and requests for the same Avida project bounds.
   Submit each request with that host's participant token and the printed
   command. Never copy alatar's private producer key to nerdanel.
6. On nerdanel, approve each pending enrollment with
   `nerdanel-approve-avida-enrollment.sh ENROLLMENT_ID OPERATOR_TOKEN_FILE`.
   It approves only realm `avida-project`, scope `avida`, and release ceiling
   `internal`. Edit the script deliberately if different bounds have been
   reviewed and agreed.

## Checks and limits

The tunnel unit refuses to replace a different existing unit file. Token and
key files are created with restrictive permissions and the scripts never
print secret contents. Token provisioning refuses to overwrite a token file.
Use distinct participant IDs and keep the operator token separate from both
participant tokens.

Enrollment does not itself transfer memory. After the two participants are
active, create a receiver-owned subscription, publish signed catalogs, and use
signed bundles for reviewed Avida project updates. Import to quarantine,
verify provenance and scope, then promote only appropriate records on the
receiving host.
