# Change Log

All notable changes to this project in this branch will be documented in this file.

## 2019-11-24

### Added
- added documentation
- extracted method advancedThroughThread from run
- extracted method waitandFire from run
- extracted collectCoro from run
- extracted gatheredFinishedSleep from event_select
- extracted sleepingThreadSleepTimer from event_select
- extracted gatherReadyEvents from event_select
- extracted performSelect from event_select
- extracted gatherWaitableandWakeupTimer from event_select

### Changed
- [bluelet.py](https://github.com/austinmm/beets/blob/Chris_Nguyen_deliverible2task3/beets/util/bluelet.py)

### Fixed

- fix several cases of long method in bluelet.py, since several functions in the file had a high complexity when used codacy to determine complexity. fixed using extract method
