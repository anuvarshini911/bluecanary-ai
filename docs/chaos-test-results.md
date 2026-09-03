# Scale & Chaos Test Results — order-service

**Date:** 2026-09-03
**Target:** order-service-active (blue-green stable service)

## Test 1: Load with mid-test chaos (via DNS — hit corporate DNS interception bug)
- 500 sequential requests via cluster DNS name
- Result: success=0, fail=500
- Root cause: same corporate DNS hijacking issue documented in D-05 (psiog.com
  network intercepts in-cluster DNS lookups). Confirmed NOT an application or
  resilience issue — retested using the Service's ClusterIP directly (see Test 2).

## Test 2: Load with mid-test chaos (via ClusterIP — clean test)
- 500 sequential requests via 10.111.62.193 (order-service-active ClusterIP)
- Chaos injected: deleted one of two running pods mid-test
- **Result: success=500, fail=0 (100% availability)**
- Kubernetes automatically detected the killed pod and scheduled a replacement
  within seconds (new pod running at 58s age by test completion), with zero
  requests failing throughout.

## Conclusion
order-service demonstrates real self-healing resilience: a pod failure during
active traffic does not cause any dropped requests, confirmed with a live
500-request test and a deliberate chaos injection (pod deletion) mid-test.
