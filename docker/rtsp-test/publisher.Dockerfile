FROM alpine:3.22

RUN apk add --no-cache ffmpeg

COPY publish.sh /usr/local/bin/publish.sh

# Protect the Linux container from Windows CRLF line endings.
RUN sed -i 's/\r$//' /usr/local/bin/publish.sh \
    && chmod 0755 /usr/local/bin/publish.sh

ENTRYPOINT ["/usr/local/bin/publish.sh"]