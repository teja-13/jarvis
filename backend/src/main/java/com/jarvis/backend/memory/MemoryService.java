package com.jarvis.backend.memory;

import org.springframework.stereotype.Service;

import java.time.Instant;
import java.util.Comparator;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;

@Service
public class MemoryService {
    private final ConcurrentMap<UUID, Memory> memories = new ConcurrentHashMap<>();

    public Memory create(MemoryRequest request) {
        var memory = new Memory(
                UUID.randomUUID(),
                request.content().trim(),
                request.source() == null || request.source().isBlank() ? "user" : request.source().trim(),
                Instant.now());
        memories.put(memory.id(), memory);
        return memory;
    }

    public List<Memory> find(String query) {
        return memories.values().stream()
                .filter(memory -> query == null || query.isBlank()
                        || memory.content().toLowerCase().contains(query.toLowerCase()))
                .sorted(Comparator.comparing(Memory::createdAt).reversed())
                .toList();
    }
}
