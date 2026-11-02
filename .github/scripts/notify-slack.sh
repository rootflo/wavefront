#!/usr/bin/env bash
# Posts the Docker vulnerability scan summary to Slack and attaches the report
# files in a thread under it. Requires: jq, curl.
#
# Usage: ./.github/scripts/notify-slack.sh summary.json [file ...]
# Env vars:
#   SLACK_BOT_TOKEN    (required) bot token with the chat:write and files:write
#                      scopes (xoxb-...)
#   SLACK_CHANNEL_ID   (optional) channel to post into; default "qa-automations"
#                      (the bot must be a member of it)
#   TEST_NAME          (optional) label shown in the Slack message
set -euo pipefail

SUMMARY_FILE="${1:-summary.json}"
shift || true
TEST_NAME="${TEST_NAME:-Docker vulnerability scan}"
SLACK_CHANNEL_ID="${SLACK_CHANNEL_ID:-qa-automations}"
SLACK_API_URL="${SLACK_API_URL:-https://slack.com/api}"

if [ -z "${SLACK_BOT_TOKEN:-}" ]; then
  echo "::warning::SLACK_BOT_TOKEN not set, skipping Slack notification" >&2
  exit 0
fi

RUN_URL="${GITHUB_SERVER_URL:-}/${GITHUB_REPOSITORY:-}/actions/runs/${GITHUB_RUN_ID:-}"

# Prints the response of a Slack API call, or exits if Slack rejected it.
check_response() {
  if [ "$(echo "$1" | jq -r '.ok')" != "true" ]; then
    echo "Slack API rejected the $2 call: $(echo "$1" | jq -r '.error')" >&2
    exit 1
  fi
  echo "$1"
}

if [ -f "$SUMMARY_FILE" ]; then
  HEADLINE=$(jq -r --arg name "$TEST_NAME" '
    (.severities.CRITICAL + .severities.HIGH) as $urgent
    | if (.failed | length) > 0 then ":x:"
      elif $urgent > 0 then ":rotating_light:"
      elif .total > 0 then ":warning:"
      else ":white_check_mark:" end
    | . + " " + $name
  ' "$SUMMARY_FILE")
  DETAILS=$(jq -r '
    "*\(.total) vulnerabilities* on `\(.ref)` (`\(.sha)`), \(.scanned) of \(.images) images scanned\n"
    + (.severities | to_entries | map("\(.key): \(.value)") | join("  ·  "))
    + "\nAccepted in .trivyignore: \(.accepted)"
    + (if (.failed | length) > 0
       then "\n*Could not be scanned, so missing from the attached reports:* \(.failed | join(", "))"
       else "" end)
  ' "$SUMMARY_FILE")
else
  HEADLINE=":x: $TEST_NAME"
  DETAILS="The report could not be generated. See the workflow run."
fi

PAYLOAD=$(jq -n \
  --arg channel "$SLACK_CHANNEL_ID" \
  --arg headline "$HEADLINE" \
  --arg details "$DETAILS" \
  --arg run_url "$RUN_URL" \
  '{
    channel: $channel,
    text: $headline,
    blocks: [
      { type: "section", text: { type: "mrkdwn", text: ("*" + $headline + "*\n" + $details) } },
      { type: "context", elements: [ { type: "mrkdwn", text: ("<" + $run_url + "|View run>") } ] }
    ]
  }')

MESSAGE=$(check_response "$(curl -sf -X POST \
  -H "Authorization: Bearer $SLACK_BOT_TOKEN" \
  -H 'Content-type: application/json; charset=utf-8' \
  --data "$PAYLOAD" \
  "$SLACK_API_URL/chat.postMessage")" chat.postMessage)

# File uploads need the channel's ID; chat.postMessage resolves the name to it.
CHANNEL=$(echo "$MESSAGE" | jq -r '.channel')
THREAD_TS=$(echo "$MESSAGE" | jq -r '.ts')

FILES='[]'
for file in "$@"; do
  if [ ! -f "$file" ]; then
    echo "::warning::$file not found, not attaching it" >&2
    continue
  fi
  UPLOAD=$(check_response "$(curl -sf -G \
    -H "Authorization: Bearer $SLACK_BOT_TOKEN" \
    --data-urlencode "filename=$(basename "$file")" \
    --data-urlencode "length=$(wc -c < "$file" | tr -d ' ')" \
    "$SLACK_API_URL/files.getUploadURLExternal")" files.getUploadURLExternal)
  curl -sf -o /dev/null -X POST --data-binary "@$file" "$(echo "$UPLOAD" | jq -r '.upload_url')"
  FILES=$(echo "$FILES" | jq \
    --arg id "$(echo "$UPLOAD" | jq -r '.file_id')" \
    --arg title "$(basename "$file")" \
    '. + [{ id: $id, title: $title }]')
done

if [ "$FILES" != '[]' ]; then
  check_response "$(curl -sf -X POST \
    -H "Authorization: Bearer $SLACK_BOT_TOKEN" \
    -H 'Content-type: application/json; charset=utf-8' \
    --data "$(jq -n --argjson files "$FILES" --arg channel "$CHANNEL" --arg ts "$THREAD_TS" \
      '{ files: $files, channel_id: $channel, thread_ts: $ts }')" \
    "$SLACK_API_URL/files.completeUploadExternal")" files.completeUploadExternal > /dev/null
fi

echo "Posted results to Slack"
