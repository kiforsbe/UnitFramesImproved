-- Stylers for Retail

local STATUS_TEXT_FONT_SIZE = 12

-- Blizzard's TextStatusBarMixin:UpdateTextStringWithValues (Blizzard_TextStatusBar)
-- calls self.numericDisplayTransformFunc(value, valueMax) when present, instead of its
-- own capNumericDisplay/BreakUpLargeNumbers formatting - an officially supported
-- extension point for exactly this. Using it means we don't have to re-implement (and
-- keep re-syncing against) Blizzard's own display-mode/percentage/prefix logic just to
-- swap in our own number abbreviation.
local function NumericDisplayTransform(value, valueMax)
  return UnitFramesImproved:AbbreviateLargeNumbers(value), UnitFramesImproved:AbbreviateLargeNumbers(valueMax)
end

-- Shared by all three frames below: set the health bar's fill texture (either
-- directly, or via a child HealthBarTexture region - Target/Focus frames use the
-- latter, Player and ToT frames use the former) and desaturate it. Font-sizing the
-- TextString/LeftText/RightText trio is optional since ToT's health bar doesn't
-- get that treatment in the original styling.
local function StyleHealthBarFill(healthBar, atlas, opts)
  opts = opts or {}

  if (opts.viaHealthBarTexture) then
    healthBar.HealthBarTexture:SetAtlas(atlas, TextureKitConstants.UseAtlasSize)
  else
    healthBar:SetStatusBarTexture(atlas, TextureKitConstants.UseAtlasSize)
  end
  healthBar:SetStatusBarDesaturated(true)

  if (opts.styleText) then
    UnitFramesImproved:SetFontSize(healthBar.TextString, STATUS_TEXT_FONT_SIZE)
    UnitFramesImproved:SetFontSize(healthBar.LeftText, STATUS_TEXT_FONT_SIZE)
    UnitFramesImproved:SetFontSize(healthBar.RightText, STATUS_TEXT_FONT_SIZE)
  end
end

function UnitFramesImproved:Style_PlayerFrame()
  if not InCombatLockdown() then
    local healthBar = PlayerFrame.PlayerFrameContent.PlayerFrameContentMain.HealthBarsContainer.HealthBar
    local manaBar = PlayerFrame.PlayerFrameContent.PlayerFrameContentMain.ManaBarArea.ManaBar

    StyleHealthBarFill(healthBar, "UI-HUD-UnitFrame-Player-PortraitOff-Bar-Health-Status", { styleText = true })

    -- Force show text
    PlayerFrame.textLockable = true
    PlayerFrame.forceShow = true

    -- Use our own number abbreviation
    healthBar.numericDisplayTransformFunc = NumericDisplayTransform
    manaBar.numericDisplayTransformFunc = NumericDisplayTransform

    -- Force an update as at least on my install, it isn't updating on load
    healthBar:UpdateTextString();

    -- Force update of the status bar coloring
    UnitFramesImproved:UpdateStatusBarColor(PlayerFrame)
  end
end

function UnitFramesImproved:Style_TargetFrame(frame)
  if not InCombatLockdown() then
    local healthBar = frame.TargetFrameContent.TargetFrameContentMain.HealthBarsContainer.HealthBar
    local manaBar = frame.TargetFrameContent.TargetFrameContentMain.ManaBar

    StyleHealthBarFill(healthBar, "UI-HUD-UnitFrame-Target-PortraitOn-Bar-Health-Status", { viaHealthBarTexture = true, styleText = true })

    -- Force show text
    frame.textLockable = true
    frame.forceShow = true

    -- Use our own number abbreviation
    healthBar.numericDisplayTransformFunc = NumericDisplayTransform
    manaBar.numericDisplayTransformFunc = NumericDisplayTransform

    -- Force update of the status bar coloring
    UnitFramesImproved:UpdateStatusBarColor(frame)
  end
end

function UnitFramesImproved:Style_ToTFrame(frame)
  if not InCombatLockdown() then
    local healthBar = frame.HealthBar

    StyleHealthBarFill(healthBar, "UI-HUD-UnitFrame-TargetofTarget-PortraitOn-Bar-Health-Status")

    -- Force update of the status bar coloring
    UnitFramesImproved:UpdateStatusBarColor(frame)
  end
end
