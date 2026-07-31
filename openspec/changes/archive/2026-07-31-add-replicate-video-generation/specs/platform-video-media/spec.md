## ADDED Requirements

### Requirement: Dedicated video file classification
The system SHALL classify MP4, MPEG video, and WebM as video formats rather than audio formats. Generic attachment analysis SHALL NOT route a classified video into audio transcription.

#### Scenario: MP4 attachment
- **WHEN** an attachment has an MP4 video MIME type or recognized MP4 video extension
- **THEN** it is classified as video and is not offered to the audio transcriber

#### Scenario: Unsupported video analysis
- **WHEN** generic media analysis receives a video without a supported video-analysis capability
- **THEN** it returns a clear unsupported-video result instead of attempting transcription

### Requirement: Telegram inbound video mapping
The Telegram API model SHALL represent inbound `Message.video` metadata, including its file identity, dimensions, duration, optional filename and MIME type, and optional size. The Telegram domain mapper SHALL map the video's caption and attachment metadata, and the existing low-level Telegram file download path SHALL resolve its bytes.

#### Scenario: Downloadable Telegram video
- **WHEN** Telegram sends a message containing a regular video within the platform download limit
- **THEN** the inbound service maps the caption, downloads the video through `TelegramBotAPI`, persists it as a chat attachment, and includes its local attachment reference in the stored message

#### Scenario: Missing Telegram MIME type
- **WHEN** Telegram omits the MIME type for a regular video
- **THEN** the mapper preserves a null MIME type rather than guessing the video's container

#### Scenario: Telegram download failure
- **WHEN** Telegram refuses the file download or returns an empty response
- **THEN** the inbound service reports the failure through the existing structured external-service error path and does not transcribe the payload as audio

### Requirement: WhatsApp inbound video mapping
The existing WhatsApp inbound video payload, caption, metadata, and authenticated media download path SHALL remain supported and SHALL persist video attachments consistently with Telegram.

#### Scenario: WhatsApp video message
- **WHEN** WhatsApp sends an inbound video message
- **THEN** the existing low-level WhatsApp API resolves the media and the inbound mapper persists the video caption and local attachment reference

#### Scenario: WhatsApp inbound regression coverage
- **WHEN** platform video support is changed
- **THEN** offline mapper and inbound-service tests continue to prove the existing WhatsApp video path

### Requirement: Portable video inspection and preparation
The system SHALL invoke the system `ffprobe` and `ffmpeg` executables through an architecture-neutral subprocess wrapper. The runtime SHALL inspect container, codecs, audio streams, dimensions, duration, and byte size before delivery and SHALL preserve an already compliant file when it meets the destination constraints.

#### Scenario: Compliant native video
- **WHEN** a generated video already satisfies the destination's container, codec, audio, dimension, and byte-size requirements
- **THEN** preparation reuses that file without lossy transcoding

#### Scenario: Conversion required
- **WHEN** a video has an incompatible container, video codec, audio codec, pixel format, streaming layout, resolution, or byte size
- **THEN** preparation converts it to MP4 with H.264 video, AAC audio when audio exists, `yuv420p`, and fast-start metadata

#### Scenario: Missing executable
- **WHEN** `ffmpeg` or `ffprobe` is unavailable
- **THEN** preparation raises a structured configuration error that identifies the missing runtime dependency

### Requirement: Bounded video preparation
The system SHALL prepare at most two videos concurrently per service instance, stream remote video bytes into temporary files instead of retaining entire videos in memory, and terminate an FFprobe or FFmpeg subprocess that exceeds five minutes.

#### Scenario: Concurrent generation completions
- **WHEN** more than two generated videos become ready at once
- **THEN** at most two enter inspection or transcoding concurrently while the remaining admitted jobs wait without loading their video bytes

#### Scenario: Preparation timeout
- **WHEN** an FFprobe or FFmpeg subprocess exceeds five minutes
- **THEN** the system terminates the subprocess, removes temporary files, releases the preparation slot, and reports a delivery failure

### Requirement: Size-aware bitrate reduction
When native platform delivery exceeds its byte limit, preparation SHALL calculate a target bitrate from the video's duration and destination byte budget, reduce resolution or bitrate as needed, and verify the resulting file before sending.

#### Scenario: First conversion fits
- **WHEN** the calculated H.264/AAC conversion produces a file within the destination limit
- **THEN** the system sends that prepared file without another conversion

#### Scenario: First conversion remains oversized
- **WHEN** the first prepared output still exceeds the destination limit
- **THEN** the system retries with a lower bitrate or resolution according to the deterministic preparation policy and verifies the retry

#### Scenario: No valid output fits
- **WHEN** preparation cannot produce a compliant file within its deadline and destination limit
- **THEN** the system does not call the native send API and reports a structured preparation failure

### Requirement: Telegram native video delivery
The Telegram integration SHALL support multipart `sendVideo` delivery of prepared MP4 files up to Telegram's native video upload limit and SHALL persist the returned outgoing message and attachment using the same chat context as other outbound media.

#### Scenario: Native Telegram send
- **WHEN** smart delivery selects native video mode
- **THEN** the Telegram SDK uploads the prepared MP4 through multipart `sendVideo`, preserves the caption, and persists the outbound result

#### Scenario: Telegram native limit
- **WHEN** the source video exceeds the native upload limit
- **THEN** the preparation layer reduces it before `sendVideo` is called

### Requirement: Telegram video preference handling
Telegram smart video delivery SHALL interpret the existing media preference as native video, file/document, or both. File delivery SHALL use multipart document upload for the original MP4 rather than relying on Telegram to fetch an MP4 URL.

#### Scenario: Native preference
- **WHEN** the media preference is photo/native
- **THEN** Telegram receives one prepared native video

#### Scenario: File preference
- **WHEN** the media preference is file
- **THEN** Telegram receives the original video as a multipart document

#### Scenario: All preference
- **WHEN** the media preference is all
- **THEN** Telegram receives the prepared native video and the original multipart document

### Requirement: WhatsApp native video delivery
The WhatsApp integration SHALL send prepared native video through the existing WhatsApp media API using an MP4 or 3GP container, H.264 video, no more than one AAC audio stream, and a maximum file size of 16 MB.

#### Scenario: Native WhatsApp send
- **WHEN** a prepared result satisfies WhatsApp's native constraints
- **THEN** the WhatsApp SDK sends the video with its caption and persists the outbound result

#### Scenario: WhatsApp conversion
- **WHEN** the provider output does not satisfy WhatsApp's native constraints
- **THEN** the preparation layer converts and reduces the output before the WhatsApp API is called

### Requirement: WhatsApp video preference handling
WhatsApp smart video delivery SHALL interpret the existing media preference as native video, file/document, or both. Native delivery SHALL use the prepared attachment, while document delivery SHALL expose the stored unresized source attachment through its public URL and include its filename.

#### Scenario: WhatsApp native preference
- **WHEN** the media preference is photo/native
- **THEN** WhatsApp receives one prepared native video

#### Scenario: WhatsApp file preference
- **WHEN** the media preference is file
- **THEN** WhatsApp receives the original video as one document

#### Scenario: WhatsApp all preference
- **WHEN** the media preference is all
- **THEN** WhatsApp receives the prepared native video and the original document

### Requirement: Outbound video attachment lifecycle
The system SHALL persist the attachment and message representation actually sent by each selected delivery path. Temporary download and transcode files SHALL be deleted after success or failure.

#### Scenario: Native video preparation
- **WHEN** native platform delivery requires conversion or size reduction
- **THEN** the system stores and sends one prepared video attachment

#### Scenario: Document delivery
- **WHEN** document delivery is selected
- **THEN** the system stores and sends one unresized source attachment

#### Scenario: Cleanup after preparation
- **WHEN** delivery succeeds or fails
- **THEN** all temporary video files are removed and the sent attachment remains governed by the existing attachment retention policy

### Requirement: Cross-platform FFmpeg environments
The implementation and CI SHALL support Debian Linux x86 production containers, macOS ARM development, and GitHub-hosted Ubuntu validation without architecture-specific Python media bindings.

#### Scenario: Production image
- **WHEN** the service Docker image is built
- **THEN** FFmpeg and FFprobe are supplied by the image's Debian package installation

#### Scenario: macOS ARM development
- **WHEN** a developer runs video preparation on macOS ARM with native FFmpeg installed
- **THEN** the same subprocess wrapper and command construction are used without an x86-only binary dependency

#### Scenario: GitHub-hosted validation
- **WHEN** offline video preparation tests run in GitHub Actions
- **THEN** the workflow makes FFmpeg available on the Ubuntu runner and exercises the portable wrapper
