-- Stylers for Retail

local STATUS_TEXT_FONT_SIZE = 12

-- NOTE ON NUMBER ABBREVIATION: we don't set a custom numericDisplayTransformFunc here.
-- Blizzard's TextStatusBarMixin:UpdateTextStringWithValues (Blizzard_TextStatusBar) calls
-- self.numericDisplayTransformFunc(value, valueMax) when one is present - but merely being
-- an addon-defined closure taints the REST of that function's execution once called,
-- regardless of what it returns. Confirmed against Blizzard_TextStatusBar/TextStatusBar.lua:
-- the transform call is at line 140, and line 170 does a plain `valueMax <= 0` check
-- afterwards - that comparison then throws "execution tainted by 'UnitFramesImproved'"
-- whenever health/mana happens to be secret at that moment, even on Blizzard's own,
-- otherwise-untainted update cycle (i.e. with no forced call from us anywhere involved).
-- There's no way to guard against this from inside our own transform function, since the
-- failure is in Blizzard's code, on a value our function never touches.
--
-- Blizzard's own capNumericDisplay path (self.capNumericDisplay, checked a few lines above
-- that same transform-func branch) calls the native AbbreviateLargeNumbers API instead,
-- which the client's own API docs mark SecretArguments = "AllowedWhenTainted" - built to be
-- safe here. UnitFrame_Initialize (Blizzard_UnitFrame/Mainline/UnitFrame.lua) already sets
-- capNumericDisplay = true on every health/mana bar unconditionally, so simply not
-- overriding it with our own transform func gets the same "abbreviated numbers" result via
-- Blizzard's own taint-safe path instead of a broken addon-owned one.

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

    StyleHealthBarFill(healthBar, "UI-HUD-UnitFrame-Player-PortraitOff-Bar-Health-Status", { styleText = true })

    -- Force show text
    PlayerFrame.textLockable = true
    PlayerFrame.forceShow = true

    -- Force an update as at least on my install, it isn't updating on load. This is
    -- our own addon code calling into Blizzard's UpdateTextString, so it runs
    -- addon-tainted; if the health value happens to be secret at that moment (seen
    -- in practice right after PLAYER_ENTERING_WORLD), Blizzard's own internal
    -- valueMax > 0 check throws rather than letting tainted code compare a secret.
    -- issecretvalue() is documented as safe to call regardless of taint, so check it
    -- up front and skip the forced call entirely instead of leaning on pcall alone -
    -- Blizzard's own (untainted) update cycle will pick the bar up on its own once
    -- the value stops being secret. pcall stays as a second line of defense in case
    -- some other field ends up secret without currValue reflecting it.
    if not (issecretvalue and issecretvalue(healthBar.currValue)) then
      pcall(healthBar.UpdateTextString, healthBar);
    end

    -- Force update of the status bar coloring
    UnitFramesImproved:UpdateStatusBarColor(PlayerFrame)
  end
end

function UnitFramesImproved:Style_TargetFrame(frame)
  if not InCombatLockdown() then
    local healthBar = frame.TargetFrameContent.TargetFrameContentMain.HealthBarsContainer.HealthBar

    StyleHealthBarFill(healthBar, "UI-HUD-UnitFrame-Target-PortraitOn-Bar-Health-Status", { viaHealthBarTexture = true, styleText = true })

    -- Force show text
    frame.textLockable = true
    frame.forceShow = true

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
