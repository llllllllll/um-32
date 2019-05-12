CXX ?= g++
OPTLEVEL ?= 3

CXXFLAGS += -Wall -Wextra -std=gnu++17 -O$(OPTLEVEL)

COW_VECTOR ?= 0
ifneq ($(COW_VECTOR),0)
	CXXFLAGS += -DUM_USE_COW_VECTOR
endif

ALL_FLAGS := 'CFLAGS=$(CFLAGS) CXXFLAGS=$(CXXFLAGS) LDFLAGS=$(LDFLAGS)'

all: um

# Write our current compiler flags so that we rebuild if they change.
force:
.compiler_flags: force
	@echo '$(ALL_FLAGS)' | cmp -s - $@ || echo '$(ALL_FLAGS)' > $@

um: machine/src/main.cc .compiler_flags
	$(CXX)  $(CXXFLAGS) $< -o $@

.PHONY: bench
bench: um
	@./etc/bench

clean:
	@rm um
