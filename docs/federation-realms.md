# Federation realms

GroundRecall federation uses one exchange substrate with separate audience
realms. A realm controls who may receive a record; it does not make a producer
authoritative at the receiver.

| Audience | Intended use | Default acceptance |
| --- | --- | --- |
| `device_local` | Host-specific notes, secrets, and raw operational state | Never exported |
| `principal` | One person's trusted devices | Automatic availability for enrolled devices; conflicts remain reviewable |
| `project` | A defined collaborative project | Quarantine and local review before durable acceptance |
| `team` | Longer-lived team or entity knowledge | Quarantine, policy, and role-based review |
| `public` | Explicitly released material | Release and publication gates |

`release_level` and `replication_audience` are independent. `private` can be
available across a principal's devices without becoming available to a project
or the public. Conversely, a project record can be `internal` or `confidential`
while remaining limited to one project realm.

Every new realm subscription should specify a realm identifier, audience,
scope (where applicable), trusted producer instances, release ceiling, and
restriction caps. Legacy subscriptions may omit these fields and retain the
pre-realm behavior; new personal and project subscriptions must be explicit.

The intended assistant path is a local-plus-federated context overlay. Remote
records may be available for relevant context while retaining their origin,
freshness, review state, and authority labels. Availability must not be
confused with local canonical acceptance.
