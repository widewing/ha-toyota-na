from abc import ABC, abstractmethod
from enum import Enum, auto, unique
from typing import Union

@unique
class VehicleFeatures(Enum):
    # Doors/Windows
    FrontDriverDoor = auto()
    FrontDriverWindow = auto()
    FrontPassengerDoor = auto()
    FrontPassengerWindow = auto()
    RearDriverDoor = auto()
    RearDriverWindow = auto()
    RearPassengerDoor = auto()
    RearPassengerWindow = auto()
    Trunk = auto()
    Moonroof = auto()
    Hood = auto()

    # Charging Status
    ChargingStatus = auto()
    
    # Numeric values
    DistanceToEmpty = auto()
    FrontDriverTire = auto()
    FrontPassengerTire = auto()
    RearDriverTire = auto()
    RearPassengerTire = auto()
    SpareTirePressure = auto()
    FuelLevel = auto()
    ChargeDistance = auto()
    ChargeDistanceAC = auto()
    ChargeLevel = auto()
    Odometer = auto()
    TripDetailsA = auto()
    TripDetailsB = auto()
    NextService = auto()
    LastTimeStamp = auto()
    LastTirePressureTimeStamp = auto()
    Speed = auto()
    PlugStatus = auto()
    RemainingChargeTime = auto()
    EvTravelableDistance = auto()
    ChargeType = auto()
    ChargeStartTime = auto()
    ChargeEndTime = auto()
    ConnectorStatus = auto()

    #Times
    OccurrenceDate = auto()

    # Engine status
    RemoteStartStatus = auto()

    # Location
    RealTimeLocation = auto()
    ParkingLocation = auto()

@unique
class RemoteRequestCommand(Enum):
    DoorLock = auto()
    DoorUnlock = auto()
    EngineStart = auto()
    EngineStop = auto()
    HazardsOn = auto()
    HazardsOff = auto()
    Refresh = auto()