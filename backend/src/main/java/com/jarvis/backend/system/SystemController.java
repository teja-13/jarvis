package com.jarvis.backend.system;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import java.time.Instant;
import java.util.Map;

@RestController
public class SystemController {
    @GetMapping("/api/health")
    public Map<String, Object> health() {
        return Map.of("status", "ok", "service", "jarvis-backend", "time", Instant.now());
    }
}
