package com.jarvis.backend.memory;

import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class MemoryServiceTest {
    @Test
    void createsAndSearchesMemories() {
        var service = new MemoryService();
        service.create(new MemoryRequest("Spring Data JPA notes", "test"));
        service.create(new MemoryRequest("A different note", "test"));

        assertThat(service.find("jpa")).hasSize(1);
        assertThat(service.find(null)).hasSize(2);
    }
}
