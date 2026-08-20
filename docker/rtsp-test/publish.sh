#!/bin/sh

set -u

RTSP_TARGET="${RTSP_TARGET:-rtsp://rtsp-server:8554/synthetic}"
RETRY_DELAY_SECONDS="${RETRY_DELAY_SECONDS:-1}"

echo "Starting synthetic RTSP publisher"
echo "Target: ${RTSP_TARGET}"

while true; do
    if ffmpeg \
        -hide_banner \
        -loglevel warning \
        -re \
        -f lavfi \
        -i "testsrc2=size=640x360:rate=15" \
        -an \
        -c:v libx264 \
        -preset ultrafast \
        -tune zerolatency \
        -pix_fmt yuv420p \
        -g 30 \
        -bf 0 \
        -f rtsp \
        -rtsp_transport tcp \
        "${RTSP_TARGET}"
    then
        echo "FFmpeg publisher exited normally"
    else
        exit_code=$?

        echo \
            "FFmpeg publisher disconnected; retrying in ${RETRY_DELAY_SECONDS}s" \
            "exit_code=${exit_code}"
    fi

    sleep "${RETRY_DELAY_SECONDS}"
done