# Assignment implementation author: Ahmed Ahmed
CXX ?= g++
CXXFLAGS ?= -std=c++17 -O3 -g -Wall -Wextra -Wpedantic
HEADERS = predictor.h branch.h trace.h my_predictor.h
.PHONY: all test sanitize extra-credit clean
all: predict
predict: predict.cc trace.cc $(HEADERS)
	$(CXX) $(CXXFLAGS) -o $@ predict.cc trace.cc
unit_tests: ../tests/test_predictor.cc $(HEADERS)
	$(CXX) $(CXXFLAGS) -I. -o $@ ../tests/test_predictor.cc
stream_test: ../tests/stream_test.cc $(HEADERS)
	$(CXX) $(CXXFLAGS) -I. -o $@ ../tests/stream_test.cc
test: predict unit_tests stream_test
	./unit_tests
	python3 ../tests/test_reference.py ./stream_test
	python3 ../tests/test_cli.py ./predict
sanitize: ../tests/test_predictor.cc $(HEADERS)
	$(CXX) -std=c++17 -O1 -g -Wall -Wextra -fsanitize=address,undefined -fno-omit-frame-pointer -I. -o unit_tests_san ../tests/test_predictor.cc
	ASAN_OPTIONS=detect_leaks=0 UBSAN_OPTIONS=halt_on_error=1 ./unit_tests_san
# The original cpm_predictor remains an unimplemented, optional extra-credit stub.
extra-credit: predict_extra_credit
predict_extra_credit: predict_extra_credit.cc trace.cc $(HEADERS)
	$(CXX) $(CXXFLAGS) -o $@ predict_extra_credit.cc trace.cc
clean:
	rm -f predict predict_extra_credit unit_tests stream_test unit_tests_san
