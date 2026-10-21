package com.jarvis.backend.memory;

import jakarta.validation.constraints.NotBlank;

public record MemoryRequest(
        @NotBlank(message = "content is required") String content,
        String source) {}
