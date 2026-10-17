#!/bin/bash
# mcp_launch.sh — start an MCP server with its secrets read from a .env file (SEC-001R).
#
# Usage: mcp_launch.sh <dir> [--only KEY[,KEY...]] [--] <command> [args...]
#
# Reads <dir>/.env, exports its keys, then execs <command>. claude_desktop_config.json
# names this script as a server's `command`, so no secret sits inline in that file
# (squiddy R-11: credentials live in .env; operator statement 2026-09-20).
#
# Why a parser and not `set -a; . .env`: a .env file is dotenv format, not shell.
# The operator's Neo4j password holds an unquoted `'`; sourcing it prints a syntax
# error and exits 0 with the key unset, i.e. the server starts without its password.
# The semantics below are python-dotenv's (the parser these repos already use, and
# test_sec001_launcher.py checks parity against it):
#   - blank lines and `#` lines are skipped; a leading `export ` is allowed
#   - KEY = VALUE, whitespace around `=` ignored
#   - '...' is literal; "..." is literal (backslash escapes refused, see below)
#   - an unquoted value ends at whitespace followed by `#` and is trimmed
#   - a key repeated later in the file wins
# Differences from python-dotenv are refusals, never silent divergence: `${` in an
# unquoted or double-quoted value (dotenv would interpolate) and a backslash inside
# double quotes (dotenv would unescape) exit 2.
#
# Precedence: a key already in the environment is kept (python-dotenv override=False,
# docker compose shell-over-.env). The config's `env` block therefore still wins
# for non-secrets such as NEO4J_DATABASE.
#
# --only limits the export to the named keys, so a server does not receive every
# credential in its repo's .env (least privilege), and fails loud if one is absent.
#
# Errors exit 2 and name the file, line and key. No value is ever printed.
# Must run under macOS /bin/bash 3.2: no associative arrays, no ${x,,}.

set -euo pipefail

die() {
    printf 'mcp_launch: %s\n' "$*" >&2
    exit 2
}

ltrim() { local s=$1; printf '%s' "${s#"${s%%[![:space:]]*}"}"; }
rtrim() { local s=$1; printf '%s' "${s%"${s##*[![:space:]]}"}"; }

[ $# -ge 1 ] || die "usage: mcp_launch.sh <dir> [--only KEY[,KEY...]] [--] <command> [args...]"
dir=$1
shift

only=""
if [ "${1:-}" = "--only" ]; then
    [ $# -ge 2 ] || die "--only needs a comma-separated key list"
    only=",$2,"
    shift 2
fi
if [ "${1:-}" = "--" ]; then
    shift
fi
[ $# -ge 1 ] || die "no command given"

envfile="$dir/.env"
[ -f "$envfile" ] || die "no .env at $envfile"
[ -r "$envfile" ] || die "cannot read $envfile"

# Keys this script exported; a later duplicate overwrites these but never a key
# that came from the environment.
ours=","
n=0
while IFS= read -r line || [ -n "$line" ]; do
    n=$((n + 1))
    line=${line%$'\r'}
    line=$(ltrim "$line")
    case $line in
        '' | '#'*) continue ;;
        'export '*) line=$(ltrim "${line#export }") ;;
    esac
    case $line in
        *=*) ;;
        *) die "$envfile:$n: not KEY=VALUE" ;;
    esac
    key=$(rtrim "${line%%=*}")
    [[ $key =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] || die "$envfile:$n: invalid key name"
    val=$(ltrim "${line#*=}")

    case $val in
        \'*)
            rest=${val#\'}
            case $rest in *\'*) ;; *) die "$envfile:$n: $key: unterminated single quote" ;; esac
            after=$(ltrim "${rest#*\'}")
            val=${rest%%\'*}
            ;;
        \"*)
            rest=${val#\"}
            case $rest in *\"*) ;; *) die "$envfile:$n: $key: unterminated double quote" ;; esac
            after=$(ltrim "${rest#*\"}")
            val=${rest%%\"*}
            case $val in *\\*) die "$envfile:$n: $key: backslash escapes unsupported" ;; esac
            case $val in *'${'*) die "$envfile:$n: $key: \${...} interpolation unsupported" ;; esac
            ;;
        *)
            after=""
            # strip from the first whitespace-then-# to the end, then trailing space
            val=$(rtrim "${val%%[[:space:]]#*}")
            case $val in *'${'*) die "$envfile:$n: $key: \${...} interpolation unsupported" ;; esac
            ;;
    esac
    case $after in
        '' | '#'*) ;;
        *) die "$envfile:$n: $key: text after closing quote" ;;
    esac

    if [ -n "$only" ]; then
        case $only in *",$key,"*) ;; *) continue ;; esac
    fi
    # $key matched the identifier regex above, so the eval is safe.
    eval "isset=\${$key+x}"
    case $ours in *",$key,"*) isset="" ;; esac
    if [ -z "$isset" ]; then
        export "$key=$val"
        ours="$ours$key,"
    fi
done <"$envfile"

if [ -n "$only" ]; then
    IFS=',' read -r -a wanted <<<"${only#,}"
    for key in "${wanted[@]}"; do
        [ -n "$key" ] || continue
        eval "isset=\${$key+x}"
        [ -n "$isset" ] || die "$key not found in $envfile or the environment"
    done
fi

exec "$@"
