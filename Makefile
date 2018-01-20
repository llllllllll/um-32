CXX ?= g++

all: um

um: src/main.cc
	$(CXX) -Wall -Wextra -std=gnu++17 -O3 $(CXXFLAGS) $< -o $@

clean:
	@rm um
