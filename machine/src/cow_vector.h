#pragma once

#include <vector>
#include <memory>

namespace um {

template<typename T, typename Alloc = std::allocator<T>>
class cow_vector {
private:
    class cow_vector_subscript final {
    private:
        cow_vector& m_vector;
        const std::size_t m_index;

    protected:
        friend class cow_vector;
        cow_vector_subscript(cow_vector& vector, std::size_t index)
            : m_vector(vector), m_index(index) {}

    public:
        template<typename U>
        T& operator=(U&& value) {
            return m_vector.assign(m_index, std::forward<U>(value));
        }

        operator const T&() const {
            return m_vector.at[m_index];
        }

        operator T&() {
            return m_vector.at(m_index);
        }
    };

    std::shared_ptr<std::vector<T, Alloc>> m_data;

    void maybe_copy() {
        if (m_data.use_count() > 1) {
            m_data = std::make_shared<std::vector<T, Alloc>>(*m_data);
        }
    }

public:
    cow_vector() : m_data(std::make_shared<std::vector<T, Alloc>>()) {}

    cow_vector(std::initializer_list<T> items)
        : m_data(std::make_shared<std::vector<T, Alloc>>(items)) {}

    cow_vector(std::size_t size, const T& value = T())
        : m_data(std::make_shared<std::vector<T, Alloc>>(size, value)) {}

    cow_vector(const cow_vector&) = default;
    cow_vector(cow_vector&&) = default;
    cow_vector& operator=(const cow_vector&) = default;
    cow_vector& operator=(cow_vector&&) = default;

    cow_vector_subscript operator[](std::size_t index) {
        return {*this, index};
    }

    const T& operator[](std::size_t index) const {
        return at(index);
    }

    template<typename U>
    T& assign(std::size_t index, U&& value) {
        maybe_copy();
        return (*m_data)[index] = std::forward<U>(value);
    }

    T& at(std::size_t index) {
        return (*m_data)[index];
    }

    const T& at(std::size_t index) const {
        return (*m_data)[index];
    }

    auto begin() {
        return m_data->begin();
    }

    auto end() {
        return m_data->end();
    }

    template<typename... Args>
    auto insert(Args&&... args) {
        maybe_copy();
        return m_data->insert(std::forward<Args>(args)...);
    }

    void clear() {
        if (m_data.use_count() > 1) {
            m_data = std::make_shared<std::vector<T, Alloc>>();
        }
        else {
            m_data->clear();
        }
    }

    const T* data() const {
        return m_data->data();
    }

    T* data() {
        return m_data->data();
    }
};
}  // namespace um
