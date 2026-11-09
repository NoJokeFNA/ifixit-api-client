# API compatibility review — 2026-11-09

The uploaded `ifixit-api-v2.json` and the [official live download](https://www.ifixit.com/api/nextjs/openapi)
were identical after parsing JSON. The snapshot contains **101 paths / 143 operations**.
Canonical JSON SHA-256 (sorted keys, compact separators):

`bf4256994a9dea81fb98947c9b903002b1dfb8372682ecd0da1ada5789249fd7`

## Changes made

- Added personal API key / OIDC Bearer headers while retaining legacy `api` tokens.
  Legacy login works without an existing token; credentials and response bodies
  are not included in request debug/error logs.
- Added required revision queries to guide publication, steps, step order, wiki
  update/delete and wiki revert. Revert sends both IDs as query parameters.
  Existing writers accept a trailing `revisionid`; methods with data may also
  read it from that dictionary. Missing IDs raise before sending an edit.
- Corrected document reads to `GET /media/documents/{id}`.
- Guide reads accept query parameters such as language, revision and XML format.
  The transport handles non-JSON responses and returns streaming responses without
  buffering them. Image upload uses binary bytes/file content plus the required
  filename query, replacing the previous incorrect JSON upload. Generic binary
  uploads preserve their content type; wildcard image types require a concrete MIME type.
- Typed models retain additional API fields instead of discarding them. `User.url`
  and `Wiki.url` are optional because live responses omit them. Guide `flags`,
  `locale`, `type`, `subject`, `summary` and timing fields survive typed parsing.
- Added `call(operation_id, ...)` for all snapshot operations, including previously
  missing Workbench, troubleshooting, media upload, patrol, search and FixBot routes.
  This is routing support with basic required-field checks, not 143 individually
  handwritten wrappers or a complete schema/permissions validator.

## Verification and limits

Regression tests use mocked writes; no account, content, media, subscription or
Workbench state was changed during this review. Public guide, user and category
wiki responses were checked against the models. Existing local HTTPS integration
tests cover CA trust, hostname verification, certificate pinning and proxy CONNECT.
The generated manifest was compared with every operation in the supplied/live
snapshot. Authenticated writes, paid chat and OIDC scopes were not tested live.

The source has limitations: legacy login inherits global security in the schema
although its prose explicitly permits unauthenticated login. Authentication is
therefore left to the server rather than enforcing that schema inheritance locally.
Documentation mixes future key requirements with current transition wording; its
explicit cutoff is January 1, 2027. An empty successful response returns `None`.

Existing legacy methods absent from the new snapshot are kept for compatibility:
cart product content, password reset, badges, guide releases, user search/SSO/email,
user PATCH and view history. Absence from OpenAPI alone does not establish that
these routes were removed; their current behavior is unverified. Category helpers
use `/wikis/CATEGORY` and `/wikis/CATEGORY/{title}`, covered by the generic wiki routes.

`call()` does not validate all nested schemas, optional parameter types, OAuth scopes
or read-only key permissions. It does not implement OAuth acquisition/refresh or
pagination for every list endpoint. Use documented per-endpoint pagination rules.
The fixed certificate pin applies to server overrides too; a FixBot request needs
that host's matching certificate when pinning is enabled. Server errors still raise
by default. A revision conflict (409) is never retried automatically.

## Legacy method deprecations

The 15 legacy methods listed below are marked with the PEP 702-compatible
`typing_extensions.deprecated` decorator. IDEs/type checkers can show the
`__deprecated__` message; calling a method emits `DeprecationWarning` and retains
its existing request behavior. Python hides this warning by default outside
`__main__`; use `python -Wd your_script.py` to show it. There is no removal deadline.
An SDK deprecation does **not** claim that iFixit has removed the server route.

| Deprecated method | Migration guidance |
|---|---|
| `get_cart_product` | No verified direct successor for cart product content. |
| `reset_password` | Use the password-reset flow on the iFixit website; no replacement API route is documented. |
| `get_badges` | For badges earned by a user, use get_user_badges(userid) or get_current_user_badges(); these are not a global badge catalog. |
| `get_badge` | No verified direct successor for a single global badge. |
| `get_guide_releases` | No verified direct successor for guide releases. |
| `delete_guide_release` | No verified direct successor for guide releases. |
| `get_guide_specific_releases` | No verified direct successor for guide releases. |
| `create_guide_release` | No verified direct successor for guide releases. |
| `update_guide_release` | No verified direct successor for guide releases. |
| `search_users` | No verified direct successor for user search; use get_user(userid) when the ID is known. |
| `get_user_by_sso` | Use get_user(userid) when the iFixit user ID is known; SSO lookup has no documented successor. |
| `get_user_by_email` | Use get_user(userid) when the iFixit user ID is known; email lookup has no documented successor. |
| `update_user` | No verified direct successor for arbitrary user updates; get_user is read-only. |
| `get_user_view_history` | No verified direct successor for view history. |
| `get_document_view_history` | No verified direct successor for view history. |

The legacy password login/token and corrected `get_document()` remain supported:
they have documented routes. For new scripts prefer `api_key` with Bearer. No
writer is silently redirected to a read-only or otherwise different operation.

## Repair-score website

The website has a separate embedded client. Its active JSON API interfaces remain
compatible: category wiki hierarchy/detail and `/guides?filter=teardown&limit=200&offset=...`.
The collector now accepts `IFIXIT_TOKEN` as Bearer and its workflow maps the Actions
secret of that name. A read-only API key must be created by the repository owner;
no key is included in the source or generated public files. API 401/403 fail a
preflight before output writes. Proxy support remains opt-in and keeps TLS validation.
Rubric/repairability HTML scraping is outside OpenAPI and retains separate parser
regression checks. No table layout or column ordering changes are part of this review.

## Updating the snapshot

Download the OpenAPI JSON from the official docs, review it as data, then run:

```sh
python tools/update_operations.py /path/to/ifixit-api-v2.json
python -m unittest discover -s tests -v
```

Review the resulting manifest diff and this report before publishing. New operation
routes do not by themselves establish compatibility of JSON schemas or permissions.

## Snapshot operation index

All operations below are callable by their exact identifier. The server enforces
credential, resource and account permissions.

| operationId | Method | Path |
|---|---|---|
| `chat` | POST | `/chat` |
| `validateMcpToken` | GET | `/oidc/mcp-token` |
| `login` | POST | `/user/token` |
| `logout` | DELETE | `/user/token` |
| `getCurrentUser` | GET | `/user` |
| `listUsers` | GET | `/users` |
| `registerUser` | POST | `/users` |
| `getUser` | GET | `/users/{userid}` |
| `getUserBadges` | GET | `/users/{userid}/badges` |
| `getCurrentUserBadges` | GET | `/user/badges` |
| `getCurrentUserWorkbenchBadges` | GET | `/user/badges/workbench` |
| `getUserFavoriteGuides` | GET | `/users/{userid}/favorites/guides` |
| `getCurrentUserFavoriteGuides` | GET | `/user/favorites/guides` |
| `favoriteGuide` | PUT | `/user/favorites/guides/{guideid}` |
| `unfavoriteGuide` | DELETE | `/user/favorites/guides/{guideid}` |
| `getUserGuides` | GET | `/users/{userid}/guides` |
| `getCurrentUserGuides` | GET | `/user/guides` |
| `getUserCompletions` | GET | `/users/{userid}/completions` |
| `getCurrentUserCompletions` | GET | `/user/completions` |
| `getUserFlags` | GET | `/user/flags` |
| `getUserImages` | GET | `/user/media/images` |
| `uploadImage` | POST | `/user/media/images` |
| `deleteImages` | DELETE | `/user/media/images/{image}` |
| `copyImageToMediaManager` | POST | `/user/media/images/{image}` |
| `rotateImageInMediaManager` | POST | `/user/media/images/{image}/rotate` |
| `getRotateImageStatus` | GET | `/user/media/images/rotate/{jobID}` |
| `getUserVideos` | GET | `/user/media/videos` |
| `uploadMedia` | POST | `/user/media/upload` |
| `listGuides` | GET | `/guides` |
| `createGuide` | POST | `/guides` |
| `getGuide` | GET | `/guides/{guideid}` |
| `updateGuide` | PATCH | `/guides/{guideid}` |
| `deleteGuide` | DELETE | `/guides/{guideid}` |
| `getGuideTags` | GET | `/guides/{guideid}/tags` |
| `addGuideTag` | PUT | `/guides/{guideid}/tag` |
| `removeGuideTag` | DELETE | `/guides/{guideid}/tag` |
| `makeGuidePublic` | PUT | `/guides/{guideid}/public` |
| `makeGuidePrivate` | DELETE | `/guides/{guideid}/public` |
| `markGuideCompleted` | PUT | `/guides/{guideid}/completed` |
| `unmarkGuideCompleted` | DELETE | `/guides/{guideid}/completed` |
| `createStep` | POST | `/guides/{guideid}/steps` |
| `updateStep` | PATCH | `/guides/{guideid}/steps/{stepid}` |
| `deleteStep` | DELETE | `/guides/{guideid}/steps/{stepid}` |
| `reorderSteps` | PUT | `/guides/{guideid}/steporder` |
| `getGuideUsers` | GET | `/guides/{guideid}/users` |
| `addGuideUser` | PUT | `/guides/{guideid}/users/{userid}` |
| `removeGuideUser` | DELETE | `/guides/{guideid}/users/{userid}` |
| `getGuideTeams` | GET | `/guides/{guideid}/teams` |
| `addGuideTeam` | PUT | `/guides/{guideid}/teams/{teamid}` |
| `removeGuideTeam` | DELETE | `/guides/{guideid}/teams/{teamid}` |
| `restoreGuide` | POST | `/guides/{guideid}/{langid}/restore` |
| `updateGuideTranslation` | PATCH | `/guides/{guideid}/{langid}` |
| `updateStepTranslation` | PATCH | `/guides/{guideid}/steps/{stepid}/{langid}` |
| `acceptGuideMetaPatrol` | POST | `/guides/patrol/meta/accept` |
| `denyGuideMetaPatrol` | POST | `/guides/patrol/meta/deny` |
| `acceptGuideStepPatrol` | POST | `/guides/patrol/step/accept` |
| `denyGuideStepPatrol` | POST | `/guides/patrol/step/deny` |
| `listTopicVariants` | GET | `/wikis/CATEGORY/{title}/topic_variants` |
| `listWikis` | GET | `/wikis/{namespace}` |
| `createWiki` | POST | `/wikis` |
| `getWiki` | GET | `/wikis/{namespace}/{title}` |
| `updateWiki` | PATCH | `/wikis/{namespace}/{title}` |
| `deleteWiki` | DELETE | `/wikis/{namespace}/{title}` |
| `revertWiki` | POST | `/wikis/{namespace}/{title}/revert` |
| `addWikiDocuments` | POST | `/wikis/{namespace}/{title}/documents` |
| `getWikiTags` | GET | `/wikis/{namespace}/{title}/tags` |
| `addWikiTag` | PUT | `/wikis/{namespace}/{title}/tag` |
| `removeWikiTag` | DELETE | `/wikis/{namespace}/{title}/tag` |
| `getWikiChildren` | GET | `/wikis/CATEGORY/{title}/children` |
| `setWikiParent` | PUT | `/wikis/CATEGORY/{title}/parent` |
| `getWikiMaintenance` | GET | `/wikis/maintenance/CATEGORY/{title}` |
| `getWikiIdentification` | GET | `/wikis/CATEGORY/{title}/identification` |
| `getWorkbenchGuides` | GET | `/wikis/CATEGORY/{title}/workbench_guides` |
| `acceptWikiPatrol` | POST | `/wikis/patrol/accept` |
| `denyWikiPatrol` | POST | `/wikis/patrol/deny` |
| `acceptWikiAreaPatrol` | POST | `/wiki_areas/patrol/accept` |
| `denyWikiAreaPatrol` | POST | `/wiki_areas/patrol/deny` |
| `listCategories` | GET | `/categories` |
| `listComments` | GET | `/comments` |
| `getComment` | GET | `/comments/{commentid}` |
| `updateComment` | PATCH | `/comments/{commentid}` |
| `deleteComment` | DELETE | `/comments/{commentid}` |
| `createComment` | POST | `/comments/{context}/{contextid}` |
| `listTags` | GET | `/tags` |
| `listTeams` | GET | `/teams` |
| `getTeam` | GET | `/teams/{teamid}` |
| `addTeamMember` | PUT | `/teams/{teamid}/users/{userid}` |
| `removeTeamMember` | DELETE | `/teams/{teamid}/users/{userid}` |
| `listRepairServices` | GET | `/teams/{teamid}/repair_services` |
| `addRepairService` | POST | `/teams/{teamid}/repair_services` |
| `reorderRepairServices` | PUT | `/teams/{teamid}/repair_services` |
| `removeRepairService` | DELETE | `/teams/{teamid}/repair_services/{wikiid}` |
| `listStories` | GET | `/stories` |
| `createStory` | POST | `/stories` |
| `getStory` | GET | `/stories/{storyid}` |
| `updateStory` | PATCH | `/stories/{storyid}` |
| `deleteStory` | DELETE | `/stories/{storyid}` |
| `search` | GET | `/search/{search}` |
| `suggest` | GET | `/suggest/{query}` |
| `getImage` | GET | `/media/images/{imageid}` |
| `getVideo` | GET | `/media/videos/{videoid}` |
| `getDocument` | GET | `/media/documents/{id}` |
| `patchDocumentMetadata` | PATCH | `/documents/{documentid}` |
| `deleteDocument` | DELETE | `/documents/{documentid}` |
| `getTroubleshooting` | GET | `/troubleshooting/{title}` |
| `getTroubleshootingByWikiid` | GET | `/troubleshooting/wikiid/{wikiid}` |
| `getProblemList` | GET | `/troubleshooting/collection/{title}` |
| `listWorkbenchItems` | GET | `/workbench/items` |
| `addWorkbenchItem` | POST | `/workbench/items` |
| `getWorkbenchItem` | GET | `/workbench/items/{workbenchItemid}` |
| `updateWorkbenchItem` | PATCH | `/workbench/items/{workbenchItemid}` |
| `removeWorkbenchItem` | DELETE | `/workbench/items/{workbenchItemid}` |
| `setActiveWorkbenchItem` | POST | `/workbench/items/{workbenchItemid}/active` |
| `listAllWorkbenchTasks` | GET | `/workbench/tasks` |
| `batchWorkbenchTasks` | POST | `/workbench/tasks/batch` |
| `listWorkbenchTasks` | GET | `/workbench/items/{workbenchItemid}/tasks` |
| `createWorkbenchTask` | POST | `/workbench/items/{workbenchItemid}/tasks` |
| `getWorkbenchTask` | GET | `/workbench/items/{workbenchItemid}/tasks/{taskid}` |
| `updateWorkbenchTask` | PATCH | `/workbench/items/{workbenchItemid}/tasks/{taskid}` |
| `deleteWorkbenchTask` | DELETE | `/workbench/items/{workbenchItemid}/tasks/{taskid}` |
| `clearActiveWorkbenchItem` | POST | `/workbench/items/clear_active` |
| `listAllWorkbenchEvents` | GET | `/workbench/events` |
| `listWorkbenchEvents` | GET | `/workbench/events/{workbenchItemid}` |
| `createWorkbenchEvent` | POST | `/workbench/events/{workbenchItemid}` |
| `getWorkbenchEvent` | GET | `/workbench/events/{workbenchItemid}/{workbenchEventid}` |
| `updateWorkbenchEvent` | PATCH | `/workbench/events/{workbenchItemid}/{workbenchEventid}` |
| `deleteWorkbenchEvent` | DELETE | `/workbench/events/{workbenchItemid}/{workbenchEventid}` |
| `getItemScheduledEvent` | GET | `/workbench/events/{workbenchItemid}/schedule/item/{scheduleid}` |
| `updateItemScheduledEvent` | PATCH | `/workbench/events/{workbenchItemid}/schedule/item/{scheduleid}` |
| `getWikiScheduledEvent` | GET | `/workbench/events/{workbenchItemid}/schedule/wiki/{scheduleid}` |
| `updateWikiScheduledEvent` | PATCH | `/workbench/events/{workbenchItemid}/schedule/wiki/{scheduleid}` |
| `listMaintenanceSchedules` | GET | `/workbench/schedules/{workbenchItemid}` |
| `createMaintenanceSchedule` | POST | `/workbench/schedules/{workbenchItemid}` |
| `getMaintenanceSchedule` | GET | `/workbench/schedules/{workbenchItemid}/{scheduleid}` |
| `updateMaintenanceSchedule` | PATCH | `/workbench/schedules/{workbenchItemid}/{scheduleid}` |
| `deleteMaintenanceSchedule` | DELETE | `/workbench/schedules/{workbenchItemid}/{scheduleid}` |
| `listItemAttachments` | GET | `/workbench/item-attachments/{workbenchItemid}` |
| `createItemAttachment` | POST | `/workbench/item-attachments/{workbenchItemid}` |
| `deleteItemAttachment` | DELETE | `/workbench/item-attachments/{workbenchItemid}/{attachmentid}` |
| `listEventAttachments` | GET | `/workbench/attachments/{workbenchItemid}/{workbenchEventid}` |
| `createEventAttachment` | POST | `/workbench/attachments/{workbenchItemid}/{workbenchEventid}` |
| `deleteEventAttachment` | DELETE | `/workbench/attachments/{workbenchItemid}/{workbenchEventid}/{attachmentid}` |
| `listWorkbenchRecommendedTools` | GET | `/workbench/recommended_tools` |
