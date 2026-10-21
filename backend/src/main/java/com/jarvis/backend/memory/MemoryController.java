package com.jarvis.backend.memory;

import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.*;

import java.util.List;

@RestController
@RequestMapping("/api/memories")
@CrossOrigin(origins = "http://localhost:3000")
public class MemoryController {
    private final MemoryService service;

    public MemoryController(MemoryService service) {
        this.service = service;
    }

    @GetMapping
    public List<Memory> list(@RequestParam(required = false) String query) {
        return service.find(query);
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    public Memory create(@Valid @RequestBody MemoryRequest request) {
        return service.create(request);
    }
}
