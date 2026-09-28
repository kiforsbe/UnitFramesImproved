-- Minimal World of Warcraft client stubs for running UnitFramesImproved outside the game.
--
-- Loaded by tests/harness.py into a fresh Lua 5.1 runtime (via lupa) for every test. Not part of
-- the addon: no TOC file lists anything under tests/, .pkgmeta ignores the folder, and build.ps1
-- only copies the files it explicitly lists.
--
-- The stubs are deliberately small and strict where it matters:
--   * Methods that aren't stubbed don't exist, so a typo'd or client-missing method call errors
--     just like it would in game ("attempt to call method ... (a nil value)").
--   * RegisterEvent rejects events the stubs don't know about, like the real client does. Add new
--     events to KNOWN_EVENTS below when the addon starts using them.
--   * Fields written onto Blizzard-owned frames/regions after setup are recorded in
--     WoWTest.fieldWrites - on Retail/Forever that's how the addon taints Blizzard's frames (see
--     ARCHITECTURE.md), so tests can assert it never happens there.
--   * SetCVar fires CVAR_UPDATE synchronously, as the real client does.
--
-- Two frame layouts are provided, matching the per-client styler split:
--   "mainline" - Retail and WoW Forever (nested PlayerFrameContent-style templates)
--   "classic"  - Mists/TBC Classic and Classic Era (flat, globally named frames); pass
--                hasFocus = false for Classic Era, which has no FocusFrame.

local WoWTest = {}
_G.WoWTest = WoWTest

WoWTest.calls = {}         -- notable global API calls, in order: { name = ..., [1..n] = args }
WoWTest.chat = {}          -- lines sent to DEFAULT_CHAT_FRAME
WoWTest.fieldWrites = {}   -- { region = name, key = key } for writes onto Blizzard-owned regions
WoWTest.inCombat = false
WoWTest.restrictions = {}  -- [Enum.AddOnRestrictionType value] = true while active
WoWTest.dispatchingRestrictionChange = false
WoWTest.classification = "normal"

local trackWrites = false
local eventFrames = {}     -- every region that can receive events, in creation order
local timers = {}
local regionData = setmetatable({}, { __mode = "k" })

local KNOWN_EVENTS = {
  ADDON_LOADED = true,
  ADDON_RESTRICTION_STATE_CHANGED = true,
  CVAR_UPDATE = true,
  PLAYER_ENTERING_WORLD = true,
  PLAYER_FOCUS_CHANGED = true,
  PLAYER_LOGIN = true,
  PLAYER_REGEN_DISABLED = true,
  PLAYER_REGEN_ENABLED = true,
  PLAYER_TARGET_CHANGED = true,
  UNIT_TARGET = true,
}

local function Log(name, ...)
  table.insert(WoWTest.calls, { name = name, ... })
end

---------------------------------------------------------------------------------------------------
-- Regions (frames, textures, font strings, status bars)
---------------------------------------------------------------------------------------------------

local Region = {}

local function Data(region)
  return regionData[region]
end

local function Record(region, method, ...)
  local calls = Data(region).calls
  calls[method] = calls[method] or {}
  table.insert(calls[method], { n = select("#", ...), ... })
end

local function NewRegion(kind, name, isBlizzard)
  local data = {
    kind = kind,
    name = name,
    isBlizzard = isBlizzard,
    shown = true,
    points = {},
    events = {},
    scripts = {},
    calls = {},
    fields = {},
    width = 100,
    height = 20,
  }

  local region = {}
  regionData[region] = data
  setmetatable(region, {
    __index = function(_, key)
      local value = data.fields[key]
      if (value ~= nil) then
        return value
      end
      return Region[key]
    end,
    __newindex = function(_, key, value)
      if (data.isBlizzard and trackWrites) then
        table.insert(WoWTest.fieldWrites, { region = data.name or kind, key = key })
      end
      data.fields[key] = value
    end,
  })

  if (name) then
    _G[name] = region
  end
  table.insert(eventFrames, region)
  return region
end

-- Blizzard-owned region: its fields are set up by the stubs themselves, and anything the addon
-- writes onto it afterwards is recorded in WoWTest.fieldWrites.
local function BlizzardRegion(kind, name, fields)
  local region = NewRegion(kind, name, true)
  for key, value in pairs(fields or {}) do
    region[key] = value
  end
  return region
end
WoWTest.BlizzardRegion = BlizzardRegion

function Region:GetName()
  return Data(self).name
end

function Region:GetObjectType()
  return Data(self).kind
end

function Region:Show()
  Record(self, "Show")
  Data(self).shown = true
end

function Region:Hide()
  Record(self, "Hide")
  Data(self).shown = false
end

function Region:IsShown()
  return Data(self).shown
end

function Region:ClearAllPoints()
  Record(self, "ClearAllPoints")
  Data(self).points = {}
end

-- Supports both SetPoint(point, relativeTo, relativePoint, x, y) and the SetPoint(point, x, y)
-- shorthand, storing the normalized five-value form GetPoint returns.
function Region:SetPoint(point, relativeTo, relativePoint, x, y)
  Record(self, "SetPoint", point, relativeTo, relativePoint, x, y)
  if (type(relativeTo) == "number") then
    relativeTo, relativePoint, x, y = nil, point, relativeTo, relativePoint
  end
  table.insert(Data(self).points, { point, relativeTo, relativePoint or point, x or 0, y or 0 })
end

function Region:GetPoint(index)
  local anchor = Data(self).points[index or 1]
  if (anchor) then
    return anchor[1], anchor[2], anchor[3], anchor[4], anchor[5]
  end
end

function Region:SetWidth(width)
  Record(self, "SetWidth", width)
  Data(self).width = width
end

function Region:SetHeight(height)
  Record(self, "SetHeight", height)
  Data(self).height = height
end

function Region:GetWidth()
  return Data(self).width
end

function Region:GetHeight()
  return Data(self).height
end

function Region:SetTexture(texture)
  Record(self, "SetTexture", texture)
  Data(self).texture = texture
end

function Region:GetTexture()
  return Data(self).texture
end

function Region:SetAtlas(atlas, useAtlasSize)
  Record(self, "SetAtlas", atlas, useAtlasSize)
  Data(self).atlas = atlas
end

function Region:SetFont(font, size, flags)
  Record(self, "SetFont", font, size, flags)
  Data(self).font = { font, size, flags }
end

function Region:GetFont()
  local font = Data(self).font or { "Fonts\\FRIZQT__.TTF", 10, "OUTLINE" }
  return font[1], font[2], font[3]
end

function Region:SetText(text)
  Record(self, "SetText", text)
  Data(self).text = text
end

function Region:GetText()
  return Data(self).text
end

function Region:SetStatusBarTexture(texture, useAtlasSize)
  Record(self, "SetStatusBarTexture", texture, useAtlasSize)
end

function Region:SetStatusBarDesaturated(desaturated)
  Record(self, "SetStatusBarDesaturated", desaturated)
end

function Region:SetStatusBarColor(r, g, b)
  Record(self, "SetStatusBarColor", r, g, b)
  Data(self).statusBarColor = { r, g, b }
end

function Region:GetStatusBarColor()
  local color = Data(self).statusBarColor or { 0, 1, 0 }
  return color[1], color[2], color[3]
end

-- Stand-in for TextStatusBarMixin:UpdateTextString on Retail/Forever bars.
function Region:UpdateTextString()
  Record(self, "UpdateTextString")
end

function Region:CreateFontString(name, layer, template)
  Record(self, "CreateFontString", name, layer, template)
  return NewRegion("FontString", name, false)
end

function Region:RegisterEvent(event)
  assert(type(event) == "string", "RegisterEvent: event must be a string")
  if (not KNOWN_EVENTS[event]) then
    error(("Attempt to register unknown event \"%s\""):format(event), 2)
  end
  Data(self).events[event] = true
end

function Region:UnregisterEvent(event)
  Data(self).events[event] = nil
end

function Region:UnregisterAllEvents()
  Data(self).events = {}
end

function Region:IsEventRegistered(event)
  return Data(self).events[event] == true
end

function Region:SetScript(scriptType, handler)
  Data(self).scripts[scriptType] = handler
end

function Region:GetScript(scriptType)
  return Data(self).scripts[scriptType]
end

function CreateFrame(frameType, name, parent, template)
  Log("CreateFrame", frameType, name)
  return NewRegion(frameType or "Frame", name, false)
end

-- Test helpers for inspecting regions.
function WoWTest.CallCount(region, method)
  local calls = Data(region).calls[method]
  return calls and #calls or 0
end

function WoWTest.LastCallArgs(region, method)
  local calls = Data(region).calls[method]
  local last = calls and calls[#calls]
  if (last) then
    return unpack(last, 1, last.n)
  end
end

function WoWTest.IsEventRegistered(region, event)
  return Data(region).events[event] == true
end

function WoWTest.CountFramesRegisteredFor(event)
  local count = 0
  for _, region in ipairs(eventFrames) do
    if (Data(region).events[event]) then
      count = count + 1
    end
  end
  return count
end

function WoWTest.StartTrackingWrites()
  trackWrites = true
end

---------------------------------------------------------------------------------------------------
-- Events, timers, combat and addon restrictions
---------------------------------------------------------------------------------------------------

function WoWTest.FireEvent(event, ...)
  assert(KNOWN_EVENTS[event], "FireEvent: unknown event " .. tostring(event))
  -- Snapshot first: handlers can (un)register events while we're dispatching.
  local receivers = {}
  for _, region in ipairs(eventFrames) do
    local data = Data(region)
    if (data.events[event] and data.scripts.OnEvent) then
      table.insert(receivers, region)
    end
  end
  for _, region in ipairs(receivers) do
    Data(region).scripts.OnEvent(region, event, ...)
  end
end

C_Timer = {}

function C_Timer.After(seconds, callback)
  table.insert(timers, callback)
end

function WoWTest.RunTimers()
  while (#timers > 0) do
    local pending = timers
    timers = {}
    for _, callback in ipairs(pending) do
      callback()
    end
  end
end

function WoWTest.PendingTimerCount()
  return #timers
end

function InCombatLockdown()
  return WoWTest.inCombat
end

function WoWTest.EnterCombat()
  WoWTest.FireEvent("PLAYER_REGEN_DISABLED")
  WoWTest.inCombat = true
end

function WoWTest.LeaveCombat()
  WoWTest.inCombat = false
  WoWTest.FireEvent("PLAYER_REGEN_ENABLED")
end

Enum = {
  AddOnRestrictionType = { Combat = 0, Encounter = 1, ChallengeMode = 2, PvPMatch = 3, Map = 4, Chat = 5 },
  AddOnRestrictionState = { Inactive = 0, Activating = 1, Active = 2 },
}

C_RestrictedActions = {}

-- Mirrors the documented behavior: always false during dispatch of ADDON_RESTRICTION_STATE_CHANGED.
function C_RestrictedActions.IsAddOnRestrictionActive(restrictionType)
  if (WoWTest.dispatchingRestrictionChange) then
    return false
  end
  return WoWTest.restrictions[restrictionType] == true
end

-- Mirrors the documented sequencing: the event fires before a restriction becomes active, and
-- after it has been deactivated.
function WoWTest.SetRestriction(name, active)
  local restrictionType = assert(Enum.AddOnRestrictionType[name], "unknown restriction " .. tostring(name))
  local states = Enum.AddOnRestrictionState

  if (not active) then
    WoWTest.restrictions[restrictionType] = nil
  end

  WoWTest.dispatchingRestrictionChange = true
  WoWTest.FireEvent("ADDON_RESTRICTION_STATE_CHANGED", restrictionType, active and states.Activating or states.Inactive)
  WoWTest.dispatchingRestrictionChange = false

  if (active) then
    WoWTest.restrictions[restrictionType] = true
  end
end

C_EventUtils = {}

function C_EventUtils.IsEventValid(event)
  return KNOWN_EVENTS[event] == true
end

---------------------------------------------------------------------------------------------------
-- CVars
---------------------------------------------------------------------------------------------------

local cvars = {
  statusText = "0",
  statusTextDisplay = "NUMERIC",
}

function GetCVar(name)
  return cvars[name]
end

function SetCVar(name, value)
  assert(cvars[name] ~= nil, "SetCVar: unknown CVar " .. tostring(name))
  value = tostring(value)
  Log("SetCVar", name, value)
  cvars[name] = value
  WoWTest.FireEvent("CVAR_UPDATE", name, value)
  return true
end

C_CVar = { GetCVar = GetCVar, SetCVar = SetCVar }

-- Sets a CVar directly, without logging or firing CVAR_UPDATE (test setup only).
function WoWTest.SetCVarSilently(name, value)
  cvars[name] = value
end

function WoWTest.SetCVarCallCount()
  local count = 0
  for _, call in ipairs(WoWTest.calls) do
    if (call.name == "SetCVar") then
      count = count + 1
    end
  end
  return count
end

---------------------------------------------------------------------------------------------------
-- Settings API (Blizzard_Settings_Shared/Blizzard_Settings.lua)
---------------------------------------------------------------------------------------------------

WoWTest.settings = { categories = {}, addOnCategories = {}, byVariable = {} }

Settings = {
  VarType = { Boolean = "boolean", String = "string", Number = "number" },
  Default = { True = true, False = false },
}

local nextCategoryID = 1000

function Settings.RegisterVerticalLayoutCategory(name)
  assert(type(name) == "string", "RegisterVerticalLayoutCategory: name must be a string")
  local category = { name = name, id = nextCategoryID, initializers = {} }
  nextCategoryID = nextCategoryID + 1
  function category:GetID()
    return self.id
  end
  function category:GetName()
    return self.name
  end

  local layout = {}
  function layout:AddInitializer(initializer)
    table.insert(category.initializers, initializer)
  end

  table.insert(WoWTest.settings.categories, category)
  return category, layout
end

function Settings.RegisterAddOnCategory(category)
  category.isAddOnCategory = true
  table.insert(WoWTest.settings.addOnCategories, category)
end

function Settings.RegisterProxySetting(category, variable, variableType, name, defaultValue, getValue, setValue)
  assert(type(variable) == "string", "RegisterProxySetting: variable must be a string")
  assert(WoWTest.settings.byVariable[variable] == nil, "RegisterProxySetting: duplicate variable " .. variable)
  assert(type(defaultValue) == variableType, "RegisterProxySetting: default value doesn't match variable type")
  assert(type(getValue) == "function" and type(setValue) == "function", "RegisterProxySetting: getter/setter required")

  local setting = { category = category, variable = variable, variableType = variableType, name = name, defaultValue = defaultValue }
  function setting:GetValue()
    return getValue()
  end
  -- Mirrors SettingMixin:ApplyValue: type-checked, and the setter only runs on an actual change.
  function setting:SetValue(value)
    assert(type(value) == self.variableType, "SetValue: value doesn't match variable type")
    if (getValue() ~= value) then
      setValue(value)
    end
  end
  function setting:GetDefaultValue()
    return self.defaultValue
  end
  function setting:GetVariable()
    return self.variable
  end
  function setting:GetName()
    return self.name
  end

  WoWTest.settings.byVariable[variable] = setting
  return setting
end

function Settings.CreateControlTextContainer()
  local container = { data = {} }
  function container:Add(value, label, tooltip)
    local entry = { value = value, label = label, text = label, tooltip = tooltip }
    table.insert(self.data, entry)
    return entry
  end
  function container:GetData()
    return self.data
  end
  return container
end

function Settings.CreateDropdown(category, setting, options, tooltip)
  local initializer = { kind = "dropdown", setting = setting, options = options, tooltip = tooltip }
  table.insert(category.initializers, initializer)
  return initializer
end

function Settings.CreateCheckbox(category, setting, tooltip)
  local initializer = { kind = "checkbox", setting = setting, tooltip = tooltip }
  table.insert(category.initializers, initializer)
  return initializer
end

function Settings.OpenToCategory(categoryID, scrollToElementName)
  Log("OpenToCategory", categoryID, scrollToElementName)
end

function Settings.GetSetting(variable)
  return WoWTest.settings.byVariable[variable]
end

---------------------------------------------------------------------------------------------------
-- Misc globals, strings and unit API
---------------------------------------------------------------------------------------------------

strlen = string.len
format = string.format
SlashCmdList = {}

DEFAULT_CHAT_FRAME = {}
function DEFAULT_CHAT_FRAME:AddMessage(message)
  table.insert(WoWTest.chat, message)
end

function print(...)
  local parts = {}
  for i = 1, select("#", ...) do
    parts[i] = tostring((select(i, ...)))
  end
  table.insert(WoWTest.chat, table.concat(parts, " "))
end

function hooksecurefunc(tableOrName, nameOrHook, hook)
  local target, name = tableOrName, nameOrHook
  if (type(tableOrName) == "string") then
    target, name, hook = _G, tableOrName, nameOrHook
  end
  local original = assert(target[name], "hooksecurefunc: no function " .. tostring(name))
  Log("hooksecurefunc", name)
  target[name] = function(...)
    local results = { original(...) }
    hook(...)
    return unpack(results)
  end
end

-- Global strings used by the options page.
STATUSTEXT_LABEL = "Status Text"
STATUS_TEXT_VALUE = "Numeric Value"
STATUS_TEXT_PERCENT = "Percentage"
STATUS_TEXT_BOTH = "Both"
NONE = "None"
OPTION_TOOLTIP_STATUS_TEXT_DISPLAY = "Display status text on unit frames."

RAID_CLASS_COLORS = { MAGE = { r = 0.25, g = 0.78, b = 0.92 } }

function UnitPlayerControlled(unit) return true end
function UnitIsTapDenied(unit) return false end
function UnitIsPlayer(unit) return unit == "player" end
function UnitIsConnected(unit) return true end
function UnitIsDeadOrGhost(unit) return false end
function UnitClass(unit) return "Mage", "MAGE" end
function UnitIsFriend(unit, otherUnit) return true end
function UnitSelectionColor(unit) return 1, 0, 0 end
function UnitClassification(unit) return WoWTest.classification end
function UnitFactionGroup(unit) return "Alliance" end
function UnitIsPVPFreeForAll(unit) return false end
function UnitIsPVP(unit) return false end
function UnitIsEnemy(unit, otherUnit) return false end

---------------------------------------------------------------------------------------------------
-- Blizzard unit frames, per client layout
---------------------------------------------------------------------------------------------------

local function TextStrings(bar)
  bar.TextString = BlizzardRegion("FontString")
  bar.LeftText = BlizzardRegion("FontString")
  bar.RightText = BlizzardRegion("FontString")
  bar.TextString:SetPoint("CENTER", bar, "CENTER", 0, 0)
  bar.LeftText:SetPoint("LEFT", bar, "LEFT", 2, 0)
  bar.RightText:SetPoint("RIGHT", bar, "RIGHT", -2, 0)
end

-- Retail and WoW Forever: nested PlayerFrameContent-style templates (Blizzard_UnitFrame/Mainline).
local function SetUpMainlineFrames()
  TextureKitConstants = { UseAtlasSize = true }

  -- Secret values only exist on Mainline clients.
  function issecretvalue(value)
    return false
  end

  local function HealthBar(withHealthBarTexture)
    local bar = BlizzardRegion("StatusBar", nil, { currValue = 100 })
    TextStrings(bar)
    if (withHealthBarTexture) then
      bar.HealthBarTexture = BlizzardRegion("Texture")
    end
    return bar
  end

  local function Content(healthBar)
    return BlizzardRegion("Frame", nil, {
      HealthBarsContainer = BlizzardRegion("Frame", nil, { HealthBar = healthBar }),
    })
  end

  BlizzardRegion("Button", "PlayerFrame", {
    unit = "player",
    PlayerFrameContent = BlizzardRegion("Frame", nil, { PlayerFrameContentMain = Content(HealthBar(false)) }),
  })

  for _, info in ipairs({ { "TargetFrame", "target" }, { "FocusFrame", "focus" } }) do
    local name, unit = info[1], info[2]
    BlizzardRegion("Button", name, {
      unit = unit,
      TargetFrameContent = BlizzardRegion("Frame", nil, { TargetFrameContentMain = Content(HealthBar(true)) }),
    })
    BlizzardRegion("Button", name .. "ToT", { unit = unit .. "target", HealthBar = HealthBar(false) })
  end
end

-- Mists/TBC Classic and Classic Era: flat, globally named frames (Blizzard_UnitFrame/Classic).
local function SetUpClassicFrames(hasFocus)
  TextStatusBarMixin = {}
  function TextStatusBarMixin:UpdateTextStringWithValues(textString, value, valueMin, valueMax)
  end

  function PlayerFrame_ToPlayerArt(self)
  end

  local function StatusBar(name, unit, x, y)
    local bar = BlizzardRegion("StatusBar", name, { unit = unit })
    bar:SetPoint("TOPLEFT", nil, "TOPLEFT", x, y)
    TextStrings(bar)
    return bar
  end

  BlizzardRegion("Button", "PlayerFrame", { unit = "player", state = "player" })
  StatusBar("PlayerFrameHealthBar", "player", 106, -41)
  StatusBar("PlayerFrameManaBar", "player", 106, -52)
  BlizzardRegion("Texture", "PlayerFrameTexture")
  BlizzardRegion("Texture", "PlayerStatusTexture")

  local function TargetFrame(name, unit)
    local frame = BlizzardRegion("Button", name, { unit = unit })
    frame.healthbar = StatusBar(name .. "HealthBar", unit, 6, -41)
    frame.manabar = StatusBar(name .. "ManaBar", unit, 6, -52)
    frame.textureFrame = BlizzardRegion("Frame")
    frame.Background = BlizzardRegion("Texture")
    frame.Background:SetPoint("BOTTOMLEFT", frame, "BOTTOMLEFT", 7, 35)
    frame.nameBackground = BlizzardRegion("Texture")
    frame.deadText = BlizzardRegion("FontString")
    frame.borderTexture = BlizzardRegion("Texture")
    frame.pvpIcon = BlizzardRegion("Texture")

    local tot = BlizzardRegion("Button", name .. "ToT", { unit = unit .. "target" })
    tot.healthbar = StatusBar(name .. "ToTHealthBar", unit .. "target", 46, -15)
  end

  TargetFrame("TargetFrame", "target")
  if (hasFocus) then
    TargetFrame("FocusFrame", "focus")
  end
end

-- flavor: "mainline" or "classic"; hasFocus only matters for "classic".
function WoWTest.Setup(flavor, hasFocus)
  if (flavor == "mainline") then
    SetUpMainlineFrames()
  elseif (flavor == "classic") then
    SetUpClassicFrames(hasFocus)
  else
    error("WoWTest.Setup: unknown flavor " .. tostring(flavor))
  end
end
