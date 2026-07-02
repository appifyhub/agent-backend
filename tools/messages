#!/usr/bin/env sh

_echo_smart() {
    color=$1
    message=$2
    if [ "$3" = "-n" ] || [ "$3" = "--newline" ]; then
        printf "$color%s\033[0m\n\n" "$message"
    else
        printf "$color%s\033[0m\n" "$message"
    fi
}

echoerr() {
    _echo_smart "\033[31m" "$1" "$2"
}

echowarn() {
    _echo_smart "\033[33m" "$1" "$2"
}

echoinfo() {
    _echo_smart "\033[94m" "$1" "$2"
}

echodebug() {
    if [ "$VERBOSE" = "true" ]; then
        _echo_smart "\033[90m" "$1" "$2"
    fi
}
