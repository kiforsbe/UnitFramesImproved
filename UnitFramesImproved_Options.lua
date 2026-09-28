-- Options page: Options -> AddOns -> UnitFramesImproved (or /ufi).
--
-- Built on Blizzard's native Settings API - the same one Blizzard's own options pages are built
-- on, and the standard way for addons to add options since Dragonflight. The older
-- InterfaceOptions_AddCategory path no longer exists at all in Midnight's or WoW Forever's UI code,
-- while every client this addon ships to (Retail, Forever, Mists/TBC Classic, Classic Era) has this
-- same Settings API with the same signatures.
--
-- The one option is Status Text: WoW Forever has no visible setting for showing health/mana
-- numbers on the unit frames, so this re-exposes Blizzard's own Status Text dropdown here. It's
-- backed by the same two CVars Blizzard's own dropdown writes
-- (Blizzard_SettingsDefinitions_Frame/Interface.lua), not by addon saved variables, so it stays in
-- sync with Blizzard's own setting wherever that still exists, and Blizzard's status bars pick it
-- up on their own without the addon writing anything onto their frames.

if (not (Settings and Settings.RegisterVerticalLayoutCategory and Settings.RegisterAddOnCategory)) then
  return
end

local STATUS_TEXT_CVAR = "statusText"
local STATUS_TEXT_DISPLAY_CVAR = "statusTextDisplay"

-- statusTextDisplay values, listed in the same order as Blizzard's own dropdown.
local MODE_NUMERIC = "NUMERIC"
local MODE_PERCENT = "PERCENT"
local MODE_BOTH = "BOTH"
local MODE_NONE = "NONE"

-- Blizzard's own default, so the "Defaults" button here and on Blizzard's own page agree.
local MODE_DEFAULT = MODE_NONE

-- Addon restrictions (Midnight/Forever) under which a unit's health/power can be a secret value.
-- Looked up by name so a client missing one of them (or the whole enum) just skips it.
local SECRET_RESTRICTION_TYPES = { "Combat", "Encounter", "ChallengeMode", "PvPMatch", "Map" }

-- A Status Text change picked while restricted, applied as soon as that ends.
local pendingStatusText

local function IsRestricted()
  if (InCombatLockdown()) then
    return true
  end

  if (C_RestrictedActions and C_RestrictedActions.IsAddOnRestrictionActive and Enum and Enum.AddOnRestrictionType) then
    for _, name in ipairs(SECRET_RESTRICTION_TYPES) do
      local restrictionType = Enum.AddOnRestrictionType[name]
      if (restrictionType and C_RestrictedActions.IsAddOnRestrictionActive(restrictionType)) then
        return true
      end
    end
  end

  return false
end

local function GetStatusText()
  if (pendingStatusText) then
    return pendingStatusText
  end

  -- The numbers only show while statusText is on as well - a leftover statusTextDisplay value on
  -- its own shows nothing (TextStatusBarMixin:UpdateTextStringWithValues hides the text unless
  -- the bar's cvar is "1"), so report that state as None rather than as the stale display mode.
  if (GetCVar(STATUS_TEXT_CVAR) ~= "1") then
    return MODE_NONE
  end

  return GetCVar(STATUS_TEXT_DISPLAY_CVAR) or MODE_NONE
end

local function SetCVarIfChanged(name, value)
  if (GetCVar(name) ~= value) then
    SetCVar(name, value)
    return true
  end
  return false
end

-- The same pair of writes Blizzard's own dropdown makes. Blizzard's status bars only redraw their
-- text for a statusText change (TextStatusBarMixin's CVAR_UPDATE handler), though - a
-- statusTextDisplay change alone (e.g. Numeric to Both) would leave the old mode's labels up until
-- each bar's value next changes. So between two shown modes, statusText is turned off and back on
-- again, the same as picking None in between; both writes land in the same frame, so nothing
-- flickers.
--
-- That handler's redraw doesn't error on secret health/power (confirmed in game on WoW Forever,
-- where UnitHealth is always secret), unlike calling UpdateTextString or firing Blizzard's
-- PROXY_STATUS_TEXT setting callback from here, which do. Unchanged CVars still aren't re-set, and
-- changes still wait out combat and addon restrictions, to keep those handler runs to a minimum.
local function ApplyStatusText(mode)
  local shown = (mode == MODE_NONE) and "0" or "1"
  local displayChanged = SetCVarIfChanged(STATUS_TEXT_DISPLAY_CVAR, mode)
  if (displayChanged and shown == "1" and GetCVar(STATUS_TEXT_CVAR) == "1") then
    SetCVar(STATUS_TEXT_CVAR, "0")
  end
  SetCVarIfChanged(STATUS_TEXT_CVAR, shown)
end

local retryFrame = CreateFrame("Frame")

local function ApplyPendingStatusText()
  if (not pendingStatusText or IsRestricted()) then
    return
  end

  local mode = pendingStatusText
  pendingStatusText = nil
  retryFrame:UnregisterAllEvents()
  ApplyStatusText(mode)
end

-- Re-check on the next frame rather than mid-dispatch: ADDON_RESTRICTION_STATE_CHANGED also fires
-- just *before* a restriction activates, and IsAddOnRestrictionActive reports false for the whole
-- dispatch of that event either way.
retryFrame:SetScript("OnEvent", function()
  C_Timer.After(0, ApplyPendingStatusText)
end)

local function SetStatusText(mode)
  if (IsRestricted()) then
    pendingStatusText = mode
    retryFrame:RegisterEvent("PLAYER_REGEN_ENABLED")
    if (C_EventUtils and C_EventUtils.IsEventValid and C_EventUtils.IsEventValid("ADDON_RESTRICTION_STATE_CHANGED")) then
      retryFrame:RegisterEvent("ADDON_RESTRICTION_STATE_CHANGED")
    end
    dout("UnitFramesImproved: Status Text will change once you're out of combat and addon restrictions have lifted.")
    return
  end

  pendingStatusText = nil
  retryFrame:UnregisterAllEvents()
  ApplyStatusText(mode)
end

local function GetStatusTextOptions()
  local container = Settings.CreateControlTextContainer()
  container:Add(MODE_NUMERIC, STATUS_TEXT_VALUE or "Numeric Value")
  container:Add(MODE_PERCENT, STATUS_TEXT_PERCENT or "Percentage")
  container:Add(MODE_BOTH, STATUS_TEXT_BOTH or "Both")
  container:Add(MODE_NONE, NONE or "None")
  return container:GetData()
end

local category = Settings.RegisterVerticalLayoutCategory("UnitFramesImproved")

local statusTextSetting = Settings.RegisterProxySetting(category, "UNITFRAMESIMPROVED_STATUS_TEXT",
  Settings.VarType.String, STATUSTEXT_LABEL or "Status Text", MODE_DEFAULT, GetStatusText, SetStatusText)
Settings.CreateDropdown(category, statusTextSetting, GetStatusTextOptions,
  OPTION_TOOLTIP_STATUS_TEXT_DISPLAY or "Shows health, mana, rage, energy and other resource values as text on the unit frames.")

Settings.RegisterAddOnCategory(category)

function UnitFramesImproved:OpenOptions()
  -- Opening the Settings panel (C_SettingsUtil.OpenSettingsPanel) is a restricted API; don't try
  -- it from addon code while in combat.
  if (InCombatLockdown()) then
    dout("UnitFramesImproved: options can't be opened in combat.")
    return
  end

  Settings.OpenToCategory(category:GetID())
end
