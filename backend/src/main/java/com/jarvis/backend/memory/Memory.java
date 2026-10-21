package com.jarvis.backend.memory;

import java.time.Instant;
import java.util.UUID;

public record Memory(UUID id, String content, String source, Instant createdAt) {}
