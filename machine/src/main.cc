#include <array>
#include <cstdint>
#include <cstdio>
#include <fstream>
#include <iostream>
#include <tuple>
#include <vector>

#include "cow_vector.h"

namespace um {
#ifdef UM_USE_COW_VECTOR
template<typename T>
using array_vector = cow_vector<T>;
#else
template<typename T>
using array_vector = std::vector<T>;
#endif

using platter = uint32_t;

enum class opcode : uint8_t {
    conditional_move = 0,
    array_index = 1,
    array_amendment = 2,
    addition = 3,
    multiplication = 4,
    division = 5,
    not_and = 6,
    halt = 7,
    allocation = 8,
    abandonment = 9,
    output = 10,
    input = 11,
    load_program = 12,
    orthography = 13,
};

std::array<std::string, 14> opname = {
    "conditional_move",
    "array_index",
    "array_amendment",
    "addition",
    "multiplication",
    "division",
    "not_and",
    "halt",
    "allocation",
    "abandonment",
    "output",
    "input",
    "load_program",
    "orthography",
};

platter extract_bits(platter p , uint8_t start, uint8_t count) {
    platter mask = ((1 << count) - 1) << start;
    return (p & mask) >> start;
}

struct malformed_program : public std::invalid_argument {
public:
    malformed_program() : std::invalid_argument("malformed_program") {}
};

class machine {
private:
    std::array<platter, 8> m_registers;
    std::vector<platter> m_free_list;
    std::vector<array_vector<platter>> m_arrays;
    std::size_t m_execution_finger;

    struct halting {};

    opcode read_opcode(platter p) {
        return static_cast<opcode>(extract_bits(p, 28, 4));
    }

    std::tuple<platter&, platter&, platter&> read_registers(platter p) {
        platter a_index = extract_bits(p, 6, 3);
        platter b_index = extract_bits(p, 3, 3);
        platter c_index = extract_bits(p, 0, 3);

        return {m_registers[a_index],
                m_registers[b_index],
                m_registers[c_index]};
    }

    void conditional_move(platter& a, platter& b, platter& c) {
        if (c) {
            a = b;
        }
    }

    void array_index(platter& a, platter& b, platter& c) {
        a = m_arrays[b][c];
    }

    void array_amendment(platter& a, platter& b, platter& c) {
        m_arrays[a][b] = c;
    }

    void addition(platter& a, platter& b, platter& c) {
        a = b + c;
    }

    void multiplication(platter& a, platter& b, platter& c) {
        a = b * c;
    }

    void division(platter& a, platter& b, platter& c) {
        a = b / c;
    }

    void not_and(platter& a, platter& b, platter& c) {
        a = ~(b & c);
    }

    void halt(platter&, platter&, platter&) {
        throw halting{};
    }

    void allocation(platter&, platter& b, platter& c) {
        if (m_free_list.size()) {
            platter address = m_free_list.back();
            m_free_list.pop_back();

            auto& vec = m_arrays[address];
            vec.insert(vec.begin(), c, 0);

            b = address;
        }
        else {
            m_arrays.emplace_back(c, 0);
            b = m_arrays.size() - 1;
        }
    }

    void abandonment(platter&, platter&, platter& c) {
        m_arrays[c].clear();
        m_free_list.push_back(c);
    }

    void output(platter&, platter&, platter& c) {
        std::putchar(c);
    }

    void input(platter&, platter&, platter& c) {
        c = std::getchar();
    }

    void load_program(platter&, platter& b, platter& c) {
        m_execution_finger = c;
        if (b) {
            m_arrays[0] = m_arrays[b];
        }
    }

    void orthography(platter& a, platter value) {
        a = value;
    }

    using instruction_impl = void (machine::*)(platter&, platter&, platter&);
    static constexpr std::array<instruction_impl, 13> m_dispatch_table {
        &machine::conditional_move,
        &machine::array_index,
        &machine::array_amendment,
        &machine::addition,
        &machine::multiplication,
        &machine::division,
        &machine::not_and,
        &machine::halt,
        &machine::allocation,
        &machine::abandonment,
        &machine::output,
        &machine::input,
        &machine::load_program,
    };

public:
    machine(const array_vector<platter>& program)
        : m_registers({0, 0, 0, 0, 0, 0, 0, 0}),
          m_arrays({program}),
          m_execution_finger(0) {}

    static machine parse(std::istream& stream) {
        stream.seekg(0, stream.end);
        std::size_t size = stream.tellg();
        stream.seekg(0);

        if (size % 4) {
            throw malformed_program();
        }

        array_vector<platter> program(size / 4, 0);

        stream.read(reinterpret_cast<char*>(program.data()), size);

        for (platter& p : program) {
            p = __builtin_bswap32(p);
        }
        return program;
    }

    void step() {
        platter instruction = m_arrays[0][m_execution_finger++];
        opcode op = read_opcode(instruction);

        if (op == opcode::orthography) {
            uint8_t a_index = extract_bits(instruction, 25, 3);
            platter value = extract_bits(instruction, 0, 25);

#ifdef UM_PRINT_TRACE
            std::cout << opname[static_cast<uint8_t>(op)]
                << '(' << static_cast<int>(a_index) << ", " << value << ")\n";
#endif

            orthography(m_registers[a_index], value);
            return;
        }

        auto registers = read_registers(instruction);

#ifdef UM_PRINT_TRACE
        std::cout << opname[static_cast<uint8_t>(op)]
                  << '(' << std::get<0>(registers)
                  << ", " << std::get<1>(registers)
                  << ", " << std::get<2>(registers)
                  << ")\n";;
#endif

        std::apply(m_dispatch_table[static_cast<uint8_t>(op)],
                   std::tuple_cat(std::make_tuple(this), std::move(registers)));
    }

    void run() {
        while (true) {
            try {
                step();
            }
            catch (halting&) {
                break;
            }
        }
    }
};
}  // namespace um


int main(int argc, char** argv) {
    if (argc != 2) {
        std::cerr << "usage: " << argv[0] << " PROGRAM\n";
        return -1;
    }

    std::fstream stream(argv[1], stream.binary | stream.in);

    try {
        um::machine::parse(stream).run();
    }
    catch (const um::malformed_program& e) {
        std::cerr << e.what() << '\n';
        return -1;
    }
    return 0;
}
