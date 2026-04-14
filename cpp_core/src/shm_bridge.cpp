#include <boost/interprocess/managed_shared_memory.hpp>
#include <boost/interprocess/sync/interprocess_mutex.hpp>
#include <boost/interprocess/sync/interprocess_condition.hpp>

#include "types.hpp"

namespace bi = boost::interprocess;

namespace bharat_alpha
{

    struct SharedSignalBuffer
    {
        bi::interprocess_mutex mutex;
        bi::interprocess_condition cond;
        bool ready;
        AlphaSignal signal;
    };

    class SharedMemoryBridge
    {
    public:
        SharedMemoryBridge()
            : segment_(bi::open_or_create, "bharat_alpha_shm", 1 << 20)
        {
            buffer_ = segment_.find_or_construct<SharedSignalBuffer>("signal_buffer")();
            buffer_->ready = false;
        }

        void publish(const AlphaSignal &sig)
        {
            bi::scoped_lock<bi::interprocess_mutex> lock(buffer_->mutex);
            buffer_->signal = sig;
            buffer_->ready = true;
            buffer_->cond.notify_one();
        }

    private:
        bi::managed_shared_memory segment_;
        SharedSignalBuffer *buffer_;
    };

} // namespace bharat_alpha
