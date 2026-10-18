CXX ?= g++
CXXFLAGS ?= -std=c++17 -O3 -Wall -Wextra -Wpedantic

.PHONY: all clean test sanitize

all: predict

predict: predict.cc trace.cc predictor.h branch.h trace.h my_predictor.h
	$(CXX) $(CXXFLAGS) -o $@ predict.cc trace.cc

../tests/test_predictor: ../tests/test_predictor.cc predictor.h branch.h my_predictor.h
	$(CXX) $(CXXFLAGS) -I. -o $@ ../tests/test_predictor.cc

test: predict ../tests/test_predictor
	../tests/test_predictor
	python3 ../tests/test_driver.py

sanitize:
	$(CXX) -std=c++17 -O1 -g -Wall -Wextra -Wpedantic -fsanitize=address,undefined -fno-omit-frame-pointer -I. -o ../tests/test_predictor_sanitize ../tests/test_predictor.cc
	../tests/test_predictor_sanitize

clean:
	rm -f predict predict_extra_credit ../tests/test_predictor ../tests/test_predictor_sanitize
